"""Full pipeline orchestrator for lateral movement detection experiments."""

from __future__ import annotations

import argparse
import io
import json
import logging
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.reporting import generate_comparison
from src.types import PipelineConfig

LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FMT,
)
logger = logging.getLogger(__name__)

_log_buffer = io.StringIO()
_buffer_handler = logging.StreamHandler(_log_buffer)
_buffer_handler.setLevel(logging.INFO)
_buffer_handler.setFormatter(logging.Formatter(LOG_FMT))
logging.getLogger().addHandler(_buffer_handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run lateral movement detection experiments."
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Limit number of events per source for quick testing",
    )
    return parser.parse_args(argv)


def _print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\nNo results to display.")
        return

    # Only include columns that exist in the DataFrame
    base_cols = ["method", "dataset", "recall", "fpr", "f1", "auc", "latency", "throughput"]
    optional_cols = ["rt_pairs_in_graph", "anomalous_pairs", "threshold"]
    cols = [c for c in base_cols + optional_cols if c in df.columns]
    display_df = df[cols].copy()
    for c in ["recall", "fpr", "f1", "auc"]:
        if c in display_df.columns:
            display_df[c] = display_df[c].map(lambda v: f"{v:.4f}")
    if "latency" in display_df.columns:
        display_df["latency"] = display_df["latency"].map(lambda v: f"{v:.2f}s")
    if "throughput" in display_df.columns:
        display_df["throughput"] = display_df["throughput"].map(lambda v: f"{v:.0f}/s")

    print("\n" + "=" * 120)
    print("EXPERIMENT RESULTS SUMMARY")
    print("=" * 120)
    print(display_df.to_string(index=False))
    print("=" * 120 + "\n")


def run(argv: list[str] | None = None) -> pd.DataFrame:
    args = _parse_args(argv)
    config: PipelineConfig = load_config()

    data_dir = config.data.lanl_dir
    window_seconds = config.data.window_size

    logger.info(f"Loading LANL data from {data_dir} (window={window_seconds}s)")

    from src.pipeline import run_streaming_experiment_variants

    all_results, results_base, combined_result = run_streaming_experiment_variants(
        data_dir=data_dir,
        window_seconds=window_seconds,
        max_events=args.sample,
        config=config,
    )

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
        dataset = r.get("dataset", "unknown")
        details[f"{dataset}/{method}"] = {k: v for k, v in r.items()}
    details_path = results_dir / "per_method_details.json"
    with open(details_path, "w") as f:
        json.dump(details, f, indent=2, default=str)
    logger.info(f"Per-method details saved to {details_path}")

    generate_comparison(results_dir=str(results_dir))

    from src.visualization import (
        plot_method_comparison,
        plot_roc_curves,
    )

    # Log plot source for evidence: graph-specific plots use combined variant only
    logger.info("Plot source: Graph and score visualizations (if generated) use combined variant only")
    if combined_result is not None:
        logger.info(f"Combined variant graph loaded for visualization: {results_base}/LANL-2015/combined/")
    else:
        logger.warning("Combined variant result not available - graph-specific visualizations cannot be generated")

    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

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

    log_path = results_dir / "pipeline_log.txt"
    _log_buffer.seek(0)
    log_path.write_text(_log_buffer.read())
    logger.info(f"Pipeline log saved to {log_path}")

    return results_df


def main() -> None:
    run()


if __name__ == "__main__":
    main()
