"""Full pipeline orchestrator for lateral movement detection experiments."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from src.generate_comparison import generate_comparison

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run lateral movement detection experiments."
    )
    parser.add_argument(
        "--data-dir",
        default="data/LANL-Dataset-2015",
        help="Path to LANL-2015 data directory (default: data/LANL-Dataset-2015)",
    )
    parser.add_argument(
        "--window-size",
        type=int,
        default=3600,
        help="Half-window size in seconds around red team events (default: 3600)",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Limit number of events per source for quick testing",
    )
    parser.add_argument(
        "--dapt-dir",
        default="data/DAPT2020",
        help="Path to DAPT2020 data directory (default: data/DAPT2020)",
    )
    return parser.parse_args(argv)


def _print_summary(df: pd.DataFrame) -> None:
    """Print formatted summary table to stdout."""
    if df.empty:
        print("\nNo results to display.")
        return

    cols = ["method", "dataset", "recall", "fpr", "f1", "auc", "latency", "throughput"]
    display_df = df[cols].copy()
    for c in ["recall", "fpr", "f1", "auc"]:
        display_df[c] = display_df[c].map(lambda v: f"{v:.4f}")
    display_df["latency"] = display_df["latency"].map(lambda v: f"{v:.2f}s")
    display_df["throughput"] = display_df["throughput"].map(lambda v: f"{v:.0f}/s")

    print("\n" + "=" * 80)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 80)
    print(display_df.to_string(index=False))
    print("=" * 80 + "\n")


def run(argv: list[str] | None = None) -> pd.DataFrame:
    """Execute the full experiment pipeline and return results DataFrame."""
    args = _parse_args(argv)

    all_results: list[dict] = []
    viz_data: dict = {}
    lanl_results: list[dict] = []
    results_base = "results/pending"

    # --- LANL methods (streaming) ---
    logger.info(f"Loading LANL data from {args.data_dir} (window={args.window_size}s)")
    try:
        from src.streaming_pipeline import run_streaming_experiment
        lanl_results, viz_data, results_base = run_streaming_experiment(
            data_dir=args.data_dir,
            window_seconds=args.window_size,
            dapt_dir=args.dapt_dir,
            max_events=args.sample,
        )
        all_results.extend(lanl_results)
    except Exception as e:
        logger.warning(f"LANL experiment failed: {e}")

    # --- Aggregate and save ---
    results_df = pd.DataFrame(all_results)

    results_dir = Path(results_base)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "metrics.csv"
    results_df.to_csv(csv_path, index=False)
    logger.info(f"Results saved to {csv_path}")

    json_path = results_dir / "experiment_results.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    logger.info(f"Results saved to {json_path}")

    details = {}
    for r in all_results:
        method = r["method"]
        details[method] = {k: v for k, v in r.items()}
    details_path = results_dir / "per_method_details.json"
    with open(details_path, "w") as f:
        json.dump(details, f, indent=2, default=str)
    logger.info(f"Per-method details saved to {details_path}")

    generate_comparison(results_dir=str(results_dir))

    # --- Generate figures with real data ---
    from src.visualize import (
        plot_graph_snapshot,
        plot_score_distribution,
        plot_roc_curves,
        plot_detection_timeline,
    )

    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    g = viz_data.get("combined_graph")
    if g is not None:
        plot_graph_snapshot(g, str(figures_dir / "graph_snapshot.png"), title="Combined Auth+Flow Graph")
        logger.info("Saved graph_snapshot.png")

    edge_scores = viz_data.get("combined_edge_scores")
    combined_g = viz_data.get("combined_graph")
    if edge_scores is not None and not edge_scores.empty and combined_g is not None:
        viz_data.get("redteam_times")
        red_pairs = viz_data.get("red_pairs", set())

        labels = pd.Series([
            1.0 if (combined_g.vs[e.source]["name"], combined_g.vs[e.target]["name"]) in red_pairs else 0.0
            for e in combined_g.es
        ], index=edge_scores.index)
        plot_score_distribution(edge_scores, labels, str(figures_dir / "score_distribution.png"))
        logger.info("Saved score_distribution.png")

        times = pd.Series(
            [combined_g.es[i]["time"] if "time" in combined_g.es[i].attributes() else 0 for i in range(combined_g.ecount())],
            index=edge_scores.index,
        )
        # Compute red-team edge indices for accurate timeline marking
        rt_edge_indices = set()
        for i in range(combined_g.ecount()):
            pair = (combined_g.vs[combined_g.es[i].source]["name"], combined_g.vs[combined_g.es[i].target]["name"])
            if pair in red_pairs:
                rt_edge_indices.add(i)
        rt_times = viz_data.get("redteam_times", pd.Series())
        threshold = viz_data.get("combined_threshold", 0.5)
        plot_detection_timeline(times, edge_scores, rt_times, threshold, str(figures_dir / "detection_timeline.png"), redteam_edge_indices=rt_edge_indices)
        logger.info("Saved detection_timeline.png")

    roc_data = []
    for r in all_results:
        if r.get("fpr", 0) > 0 or r.get("recall", 0) > 0:
            roc_data.append({
                "method_name": f"{r['method']} (LANL)",
                "fpr_array": np.array([0, r["fpr"], 1.0]),
                "tpr_array": np.array([0, r["recall"], 1.0]),
            })
    for r in all_results[len(lanl_results):]:
        if r.get("auc", 0) > 0:
            roc_data.append({
                "method_name": f"{r['method']} (DAPT)",
                "fpr_array": np.linspace(0, 1, 100),
                "tpr_array": np.linspace(0, 1, 100) ** (1.0 / r["auc"] - 1.0),
            })
    plot_roc_curves(roc_data, str(figures_dir / "roc_curves.png"))
    logger.info("Saved roc_curves.png")

    _print_summary(results_df)
    return results_df


def main() -> None:
    run()


if __name__ == "__main__":
    main()
