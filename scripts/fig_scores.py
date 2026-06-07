"""Generate score distribution figure (combined variant)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd

from scripts._common import parse_args, apply_paper_style, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_results
from src.figures.loading import load_edge_scores
from src.visualization.scores import plot_score_distribution


def main() -> None:
    args = parse_args("Generate score distribution figure")
    apply_paper_style()
    output_dir = resolve_output_dir()

    results_dir = find_latest_results(args.run_id)
    ensure_data_or_fail(results_dir, "Error: No results directory found. Run 'make results' first.")

    variant = "combined"
    df = load_edge_scores(results_dir, variant)
    ensure_data_or_fail(df if df is not None else None, f"Error: No edge scores found for variant '{variant}'.")

    score_col = next((c for c in ("score", "edge_score", "anomaly_score") if c in df.columns), None)
    label_col = next((c for c in ("is_redteam", "red_team", "redteam", "label") if c in df.columns), None)
    ensure_data_or_fail(score_col, "Error: No score column found in edge scores.")

    scores = pd.to_numeric(df[score_col], errors="coerce").dropna()
    ensure_data_or_fail(scores if not scores.empty else None, "Error: No valid scores after cleanup.")

    labels = (
        pd.to_numeric(df[label_col], errors="coerce").fillna(0).astype(int)
        if label_col
        else pd.Series(0, index=df.index)
    )

    plot_score_distribution(scores, labels, str(output_dir / "score_distribution.png"))


if __name__ == "__main__":
    main()
