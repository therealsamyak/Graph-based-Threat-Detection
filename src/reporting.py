"""Generate comparison table and summary from experiment results."""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def generate_comparison(results_dir: str = "results") -> None:
    """Load metrics.csv, create comparison_table.md and summary.txt.

    If metrics.csv doesn't exist, writes placeholder files.
    """
    results_path = Path(results_dir)
    metrics_path = results_path / "metrics.csv"
    comp_path = results_path / "comparison_table.md"
    summ_path = results_path / "summary.txt"
    results_path.mkdir(parents=True, exist_ok=True)

    if not metrics_path.exists():
        comp_path.write_text(
            "# Lateral Movement Detection — Method Comparison\n\n"
            "> **No results yet.** Run `uv run python run_experiment.py --sample 10000` "
            "to generate results.\n"
        )
        summ_path.write_text(
            "No results yet. Run: uv run python run_experiment.py --sample 10000\n"
        )
        logger.info(f"Placeholder files created in {results_path}/")
        return

    df = pd.read_csv(metrics_path)

    # comparison_table.md
    metric_cols = ["recall", "fpr", "f1", "auc", "latency", "throughput"]
    avail = [c for c in metric_cols if c in df.columns]

    md = "# Lateral Movement Detection — Method Comparison\n\n"
    header = "| Method | Dataset | " + " | ".join(m.capitalize() for m in avail) + " |\n"
    sep = "|--------|---------|" + "|".join(["------" for _ in avail]) + "|\n"
    md += header + sep

    for _, row in df.iterrows():
        vals = []
        for m in avail:
            v = row.get(m, 0)
            if pd.isna(v):
                v = 0
            if m in ("latency",):
                vals.append(f"{v:.2f}s")
            elif m in ("throughput",):
                vals.append(f"{v:.0f}/s")
            else:
                vals.append(f"{v:.4f}")
        md += f"| {row['method']} | {row.get('dataset', 'N/A')} | " + " | ".join(vals) + " |\n"

    # Best per metric
    md += "\n## Best Method Per Metric\n\n"
    for m in ["recall", "f1", "auc"]:
        if m in df.columns and not df[m].dropna().empty:
            best_idx = df[m].idxmax()
            best = df.loc[best_idx]
            md += f"- **Best {m}**: {best['method']} ({best.get('dataset', 'N/A')} — {best[m]:.4f})\n"
    if "fpr" in df.columns and not df["fpr"].dropna().empty:
        best_idx = df["fpr"].idxmin()
        best = df.loc[best_idx]
        md += f"- **Lowest FPR**: {best['method']} ({best.get('dataset', 'N/A')} — {best['fpr']:.4f})\n"

    # Relative improvement: combined vs single-source
    if "dataset" in df.columns:
        lanl = df[df["dataset"] == "LANL-2015"]
        if not lanl.empty and "combined" in lanl["method"].values:
            combined = lanl[lanl["method"] == "combined"].iloc[0]
            singles = lanl[lanl["method"].isin(["flow_only", "auth_only"])]
            md += "\n## Relative Improvement: Combined vs Single-Source\n\n"
            for _, s in singles.iterrows():
                md += f"### Combined vs {s['method']}\n"
                for m in ["recall", "f1"]:
                    if s[m] > 0:
                        imp = ((combined[m] - s[m]) / s[m]) * 100
                        md += f"- {m}: {imp:+.1f}%\n"

    comp_path.write_text(md)

    # summary.txt
    lines = [
        "LATERAL MOVEMENT DETECTION — KEY FINDINGS",
        "=" * 50,
        "",
    ]

    if "dataset" in df.columns:
        lanl = df[df["dataset"] == "LANL-2015"]
        if not lanl.empty:
            lines.append("LANL-2015 Results:")
            for _, row in lanl.iterrows():
                lines.append(
                    f"  {row['method']}: recall={row.get('recall', 0):.4f}, "
                    f"f1={row.get('f1', 0):.4f}, fpr={row.get('fpr', 0):.4f}"
                )
            lines.append("")
            if "combined" in lanl["method"].values:
                combined = lanl[lanl["method"] == "combined"].iloc[0]
                best_single = lanl[lanl["method"] != "combined"]
                if not best_single.empty:
                    best_recall = best_single["recall"].max()
                    lines.append(
                        f"Combined method recall: {combined['recall']:.4f} "
                        f"(best single-source: {best_recall:.4f})"
                    )

        dapt = df[df["dataset"] == "DAPT2020"]
        if not dapt.empty:
            lines.append("\nDAPT2020 Baseline Results:")
            for _, row in dapt.iterrows():
                auc_val = row.get('auc', 0)
                if pd.isna(auc_val):
                    auc_val = 0
                lines.append(
                    f"  {row['method']}: auc={auc_val:.4f}, "
                    f"f1={row.get('f1', 0):.4f}"
                )
    else:
        lines.append("All results:")
        for _, row in df.iterrows():
            lines.append(f"  {row['method']}: {dict(row)}")

    lines.append("")
    lines.append("Key Takeaways:")
    lines.append("  - Run `uv run python run_experiment.py --sample 10000` to populate")
    lines.append("  - Combined auth+flow graph method vs single-source baselines")
    lines.append("  - Graph-based approach vs DAPT2020 ML baselines (OneClassSVM, IF)")

    summ_path.write_text("\n".join(lines))
    logger.info(f"Generated comparison_table.md and summary.txt in {results_path}/")
