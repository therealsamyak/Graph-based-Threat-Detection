"""Generate graph statistics figure."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_results

def main():
    args = parse_args("Generate graph statistics figure")
    apply_paper_style()
    output_dir = resolve_output_dir()

    results_dir = find_latest_results(args.run_id)
    ensure_data_or_fail(results_dir, "Error: No results directory found. Run 'make results' first.")

    from src.figures.detection import plot_graph_statistics
    plot_graph_statistics(results_dir, output_dir)

if __name__ == "__main__":
    main()
