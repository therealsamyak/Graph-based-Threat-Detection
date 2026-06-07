"""Generate anomaly score distribution figures per variant."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_results, find_latest_baselines


def main() -> None:
    args = parse_args("Generate anomaly score distribution figures")
    apply_paper_style()
    output_dir = resolve_output_dir()

    results_dir = find_latest_results(args.run_id)
    ensure_data_or_fail(results_dir, "Error: No results directory found. Run 'make results' first.")

    baselines_dir = find_latest_baselines()
    ensure_data_or_fail(baselines_dir, "Error: No baseline results directory found. Run 'make baselines' first.")

    from src.figures.detection import plot_score_distributions

    plot_score_distributions(results_dir, baselines_dir, output_dir)


if __name__ == "__main__":
    main()
