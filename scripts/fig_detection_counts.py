"""Generate detection-counts figure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_results, find_latest_baselines
from src.figures.loading import load_per_method_details, load_baseline_summary, build_method_variant_matrix


def main():
    args = parse_args("Generate detection-counts figure")
    apply_paper_style()
    output_dir = resolve_output_dir()

    results_dir = find_latest_results(args.run_id)
    ensure_data_or_fail(results_dir, "Error: No results directory found. Run 'make results' first.")

    baselines_dir = find_latest_baselines()
    ensure_data_or_fail(baselines_dir, "Error: No baseline results directory found. Run 'make baselines' first.")

    per_method_details = load_per_method_details(results_dir)
    baseline_summary = load_baseline_summary(baselines_dir)
    matrix = build_method_variant_matrix(per_method_details, baseline_summary)
    ensure_data_or_fail(matrix if not matrix.empty else None, "Error: Could not build method×variant matrix.")

    from src.figures.comparison import plot_detection_counts
    plot_detection_counts(matrix, output_dir)


if __name__ == "__main__":
    main()
