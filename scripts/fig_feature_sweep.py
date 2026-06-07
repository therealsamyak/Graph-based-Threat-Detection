"""Generate feature sweep figure."""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_analysis
from src.figures.loading import load_analysis_results

def main():
    args = parse_args("Generate feature sweep figure")
    apply_paper_style()
    output_dir = resolve_output_dir()

    analysis_dir = find_latest_analysis()
    ensure_data_or_fail(analysis_dir, "Error: No analysis results directory found.")

    analysis_data = load_analysis_results(analysis_dir)
    ensure_data_or_fail(analysis_data, "Error: Could not load analysis results.")

    from src.figures.features import plot_feature_sweep
    plot_feature_sweep(analysis_data, output_dir)

if __name__ == "__main__":
    main()
