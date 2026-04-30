"""Full pipeline orchestrator for lateral movement detection experiments."""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

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

    # --- LANL methods (streaming) ---
    logger.info(f"Loading LANL data from {args.data_dir} (window={args.window_size}s)")
    try:
        from src.streaming_pipeline import run_streaming_experiment
        lanl_results = run_streaming_experiment(
            data_dir=args.data_dir,
            window_seconds=args.window_size,
            dapt_dir=args.dapt_dir,
        )
        all_results.extend(lanl_results)
    except Exception as e:
        logger.warning(f"LANL experiment failed: {e}")

    # --- Aggregate and save ---
    results_df = pd.DataFrame(all_results)

    results_dir = Path("results")
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / "metrics.csv"
    results_df.to_csv(csv_path, index=False)
    logger.info(f"Results saved to {csv_path}")

    generate_comparison()

    _print_summary(results_df)
    return results_df


def main() -> None:
    run()


if __name__ == "__main__":
    main()
