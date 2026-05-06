"""Full pipeline orchestrator for lateral movement detection experiments."""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.reporting import generate_comparison
from src.types import ExperimentResult, PipelineConfig
from src.utils import compute_edge_pair_names

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
        default="datasets/LANL-Dataset-2015",
        help="Path to LANL-2015 data directory (default: datasets/LANL-Dataset-2015)",
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
        default="datasets/dapt2020",
        help="Path to DAPT2020 data directory (default: datasets/dapt2020)",
    )
    return parser.parse_args(argv)


def _print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\nNo results to display.")
        return

    cols = ["method", "dataset", "recall", "fpr", "f1", "auc", "latency", "throughput",
            "rt_pairs_in_graph", "anomalous_pairs", "threshold"]
    display_df = df[cols].copy()
    for c in ["recall", "fpr", "f1", "auc"]:
        display_df[c] = display_df[c].map(lambda v: f"{v:.4f}")
    display_df["latency"] = display_df["latency"].map(lambda v: f"{v:.2f}s")
    display_df["throughput"] = display_df["throughput"].map(lambda v: f"{v:.0f}/s")

    print("\n" + "=" * 120)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 120)
    print(display_df.to_string(index=False))
    print("=" * 120 + "\n")


def run(argv: list[str] | None = None) -> pd.DataFrame:
    args = _parse_args(argv)
    config: PipelineConfig = load_config()

    _DEFAULTS = {"data_dir": "datasets/LANL-Dataset-2015", "window_size": 3600, "dapt_dir": "datasets/dapt2020"}
    data_overrides: dict = {}
    if args.data_dir != _DEFAULTS["data_dir"]:
        data_overrides["lanl_dir"] = args.data_dir
    if args.window_size != _DEFAULTS["window_size"]:
        data_overrides["window_size"] = args.window_size
    if args.dapt_dir != _DEFAULTS["dapt_dir"]:
        data_overrides["dapt_dir"] = args.dapt_dir
    if data_overrides:
        config = config.with_overrides(data=data_overrides)

    all_results: list[dict] = []
    experiment_result: ExperimentResult | None = None
    results_base = "results/pending"

    logger.info(f"Loading LANL data from {args.data_dir} (window={args.window_size}s)")
    try:
        from src.pipeline import run_streaming_experiment
        lanl_results, experiment_result, results_base = run_streaming_experiment(
            data_dir=args.data_dir,
            window_seconds=args.window_size,
            dapt_dir=args.dapt_dir,
            max_events=args.sample,
            config=config,
        )
        all_results.extend(lanl_results)
    except Exception as e:
        logger.warning(f"LANL experiment failed: {e}")

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

    from src.visualization import (
        plot_graph_snapshot,
        plot_score_distribution,
        plot_roc_curves,
        plot_detection_timeline,
        plot_method_comparison,
    )

    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    g = experiment_result.combined_graph if experiment_result else None
    if g is not None:
        plot_graph_snapshot(g, str(figures_dir / "graph_snapshot.png"), title=f"Combined Auth+Flow Graph ({g.vcount():,} nodes, {g.ecount():,} edges)")
        logger.info("Saved graph_snapshot.png")

    edge_scores = experiment_result.combined_edge_scores if experiment_result else None
    if edge_scores is not None and not edge_scores.empty and g is not None:
        red_pairs = experiment_result.red_pairs
        threshold = experiment_result.combined_threshold

        edge_pair_names = compute_edge_pair_names(g)
        labels = pd.Series([
            1.0 if pair in red_pairs else 0.0
            for pair in edge_pair_names
        ], index=edge_scores.index)
        plot_score_distribution(edge_scores, labels, str(figures_dir / "score_distribution.png"), threshold=threshold, title="Edge Anomaly Score Distribution")
        logger.info("Saved score_distribution.png")

        times = pd.Series(
            [g.es[i]["time"] if "time" in g.es[i].attributes() else 0 for i in range(g.ecount())],
            index=edge_scores.index,
        )
        rt_edge_indices = {i for i, pair in enumerate(edge_pair_names) if pair in red_pairs}
        plot_detection_timeline(times, edge_scores, threshold, str(figures_dir / "detection_timeline.png"), redteam_edge_indices=rt_edge_indices, title="Anomaly Score Timeline with Red Team Events")
        logger.info("Saved detection_timeline.png")

    roc_data = []
    for r in all_results:
        if r.get("auc", 0) > 0:
            roc_data.append({
                "method_name": f"{r['method']} ({r['dataset']})",
                "auc": r["auc"],
            })
    plot_roc_curves(roc_data, str(figures_dir / "roc_curves.png"), title="ROC Curves — Lateral Movement Detection Methods")
    logger.info("Saved roc_curves.png")

    plot_method_comparison(all_results, str(figures_dir / "method_comparison.png"), title="Method Performance Comparison")
    logger.info("Saved method_comparison.png")

    _print_summary(results_df)
    return results_df


def main() -> None:
    run()


if __name__ == "__main__":
    main()
