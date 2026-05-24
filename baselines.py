"""Baseline testing: One-Class SVM and Isolation Forest for threat detection comparison.

Usage:
    uv run baselines.py                                    # Run on latest results
    uv run baselines.py --run_id 20260520_110758           # Run on specific run_id
    uv run baselines.py --run_id 20260520_110758 --variant combined  # Specific variant
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from src.baselines import run_baselines
from src.variants import list_variants

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Baseline testing: One-Class SVM and Isolation Forest for threat detection comparison"
    )
    parser.add_argument(
        "--run_id",
        type=str,
        default=None,
        help="Specific run_id to evaluate (e.g., 20260520_110758). Defaults to latest.",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        choices=list(list_variants()),
        help="Evaluate specific variant. Default: evaluate all found variants.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory to search for cached runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("baseline_results"),
        help="Output directory for baseline results.",
    )
    return parser.parse_args(argv)


def main() -> None:
    args = _parse_args()
    run_baselines(
        results_dir=args.results_dir,
        output_dir=args.output_dir,
        run_id=args.run_id,
        variant=args.variant,
    )


if __name__ == "__main__":
    main()
