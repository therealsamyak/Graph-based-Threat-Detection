"""Full pipeline orchestrator for lateral movement detection experiments."""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

from src.baselines.dapt_baselines import run_dapt_baselines
from src.baselines.single_source import (
    run_auth_only_baseline,
    run_combined_method,
    run_flow_only_baseline,
)
from src.data_loader import load_lanl_data
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


def _run_lanl_method(fn, auth_df, flow_df, redteam_df, window_seconds):
    """Run a single LANL baseline method with timing."""
    t0 = time.perf_counter()
    result = fn(auth_df, flow_df, redteam_df, window_seconds=window_seconds)
    elapsed = time.perf_counter() - t0
    result["latency"] = round(elapsed, 4)
    total_events = len(auth_df) + len(flow_df)
    result["throughput"] = round(total_events / elapsed, 2) if elapsed > 0 else 0.0
    return result


def _normalize_lanl_result(result: dict) -> dict:
    """Normalize LANL result to common format."""
    return {
        "method": result.get("method_name", "unknown"),
        "dataset": "LANL-2015",
        "recall": result.get("recall", 0.0),
        "fpr": result.get("fpr", 0.0),
        "f1": result.get("f1", 0.0),
        "auc": 0.0,
        "latency": result.get("latency", 0.0),
        "throughput": result.get("throughput", 0.0),
    }


def _normalize_dapt_result(result: dict) -> dict:
    """Normalize DAPT result to common format."""
    return {
        "method": result.get("method_name", "unknown"),
        "dataset": "DAPT2020",
        "recall": result.get("recall", 0.0),
        "fpr": result.get("fpr", 0.0),
        "f1": result.get("f1", 0.0),
        "auc": result.get("auc", 0.0),
        "latency": 0.0,
        "throughput": 0.0,
    }


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

    # --- LANL methods ---
    logger.info(f"Loading LANL data from {args.data_dir} (window={args.window_size}s)")
    try:
        data = load_lanl_data(
            args.data_dir,
            window_seconds=args.window_size,
            max_events=args.sample,
        )
        auth_df = data["auth"]
        flow_df = data["flows"]
        redteam_df = data["redteam"]
        logger.info(
            f"Loaded {len(auth_df)} auth events, {len(flow_df)} flow events, "
            f"{len(redteam_df)} red team events"
        )

        lanl_methods = [
            ("flow_only", run_flow_only_baseline),
            ("auth_only", run_auth_only_baseline),
            ("combined", run_combined_method),
        ]

        for name, fn in lanl_methods:
            try:
                logger.info(f"Running LANL method: {name}")
                result = _run_lanl_method(fn, auth_df, flow_df, redteam_df, args.window_size)
                all_results.append(_normalize_lanl_result(result))
                logger.info(f"  {name}: recall={result['recall']:.4f}, f1={result['f1']:.4f}")
            except Exception as e:
                logger.warning(f"LANL method '{name}' failed: {e}")
                continue
    except Exception as e:
        logger.warning(f"LANL data loading failed: {e}")

    # --- DAPT baselines ---
    logger.info("Running DAPT2020 baselines")
    try:
        dapt_results = run_dapt_baselines(data_dir=args.dapt_dir)
        for r in dapt_results:
            all_results.append(_normalize_dapt_result(r))
            logger.info(f"  {r['method_name']}: auc={r['auc']:.4f}, f1={r['f1']:.4f}")
    except Exception as e:
        logger.warning(f"DAPT baselines failed: {e}")

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
