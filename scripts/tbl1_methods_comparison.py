"""Generate methods comparison table (markdown)."""

import math
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts._common import parse_args, resolve_output_dir, ensure_data_or_fail
from src.figures.discovery import find_latest_results, find_latest_baselines
from src.figures.loading import (
    load_per_method_details,
    load_baseline_summary,
    build_method_variant_matrix,
)

_DISPLAY_NAMES = {
    "graph_based": "Graph-Based",
    "one_class_svm": "One-Class SVM",
    "isolation_forest": "Isolation Forest",
}

_VARIANT_LABELS = {
    "combined": "Combined",
    "auth_only": "Auth Only",
    "flow_only": "Flow Only",
}


def _fmt_val(v: object) -> str:
    try:
        f = float(str(v))
    except (TypeError, ValueError):
        return "—"
    if not math.isfinite(f):
        return "—"
    return f"{f:.4f}"


def main() -> None:
    args = parse_args("Generate methods comparison table")
    output_dir = resolve_output_dir()

    results_dir = find_latest_results(args.run_id)
    ensure_data_or_fail(
        results_dir, "Error: No results directory found. Run 'make results' first."
    )

    baselines_dir = find_latest_baselines()
    ensure_data_or_fail(
        baselines_dir,
        "Error: No baseline results directory found. Run 'make baselines' first.",
    )

    per_method_details = load_per_method_details(results_dir)
    baseline_summary = load_baseline_summary(baselines_dir)
    matrix = build_method_variant_matrix(per_method_details, baseline_summary)
    ensure_data_or_fail(
        matrix if not matrix.empty else None,
        "Error: Could not build method×variant matrix.",
    )

    metric_cols = ["recall", "fpr", "f1", "auc", "precision"]
    avail = [c for c in metric_cols if c in matrix.columns]

    md = "# Lateral Movement Detection — Method Comparison\n\n"
    header = "| Method | Variant | " + " | ".join(m.capitalize() for m in avail) + " |\n"
    sep = "|--------|---------|" + "|".join(["------" for _ in avail]) + "|\n"
    md += header + sep

    for _, row in matrix.iterrows():
        method_key = str(row["method"])
        variant_key = str(row["variant"])
        method = _DISPLAY_NAMES.get(method_key, method_key)
        variant = _VARIANT_LABELS.get(variant_key, variant_key)
        vals = [_fmt_val(row.get(m)) for m in avail]
        md += f"| {method} | {variant} | " + " | ".join(vals) + " |\n"

    md += "\n## Best Method Per Metric\n\n"
    for m in ["recall", "f1", "auc"]:
        if m in matrix.columns:
            col_data = matrix[m].dropna()
            if not col_data.empty:
                best = matrix.loc[col_data.idxmax()]
                bk = str(best["method"])
                bv = str(best["variant"])
                md += (
                    f"- **Best {m}**: "
                    f"{_DISPLAY_NAMES.get(bk, bk)} "
                    f"({_VARIANT_LABELS.get(bv, bv)}) "
                    f"— {best[m]:.4f}\n"
                )
    if "fpr" in matrix.columns:
        col_data = matrix["fpr"].dropna()
        if not col_data.empty:
            best = matrix.loc[col_data.idxmin()]
            bk = str(best["method"])
            bv = str(best["variant"])
            md += (
                f"- **Lowest FPR**: "
                f"{_DISPLAY_NAMES.get(bk, bk)} "
                f"({_VARIANT_LABELS.get(bv, bv)}) "
                f"— {best['fpr']:.4f}\n"
            )

    output_path = output_dir / "methods_comparison.md"
    output_path.write_text(md)
    print(f"Generated: {output_path}")


if __name__ == "__main__":
    main()
