"""Markdown reporting for feature audit results."""

from __future__ import annotations

from pathlib import Path

from src.feature_audit.types import AuditReport


def _fmt(value: float) -> str:
    return f"{value:.6g}"


def generate_report(audit: AuditReport) -> str:
    lines = [
        "# Feature Audit Results",
        "",
        "## Summary",
        "",
        f"- Calibration edges: {audit.calibration_n:,} ({audit.redteam_calibration:,} redteam)",
        f"- Evaluation edges: {audit.eval_n:,} ({audit.redteam_eval:,} redteam)",
        f"- AUC threshold: {audit.config.min_auc}",
        f"- Selected features: {len(audit.selected_features)}",
        "",
        "## Selected Features",
        "",
    ]
    lines.extend(f"- `{feature}`" for feature in audit.selected_features)
    if not audit.selected_features:
        lines.append("- None")
    lines.extend(
        [
            "",
            "## Ranked Features",
            "",
            "| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |",
            "|---|---:|---:|---:|---:|---:|---:|---|---:|",
        ]
    )
    for result in audit.features:
        eval_auc = audit.eval_metrics.get(result.feature, 0.0)
        lines.append(
            "| "
            + " | ".join(
                [
                    result.feature,
                    _fmt(result.auc),
                    str(result.n_unique),
                    _fmt(result.variance),
                    _fmt(result.mean_redteam),
                    _fmt(result.mean_benign),
                    _fmt(result.delta_mean),
                    "yes" if result.selected else "no",
                    _fmt(eval_auc) if eval_auc else "",
                ]
            )
            + " |"
        )
    lines.extend(["", "## Duplicate Features", ""])
    if audit.duplicate_pairs:
        lines.extend(f"- `{duplicate}` duplicates `{original}`" for original, duplicate in audit.duplicate_pairs)
    else:
        lines.append("- None detected")
    lines.extend(
        [
            "",
            "## Recommendations",
            "",
            "### Top 5 Features",
            "",
        ]
    )
    lines.extend(f"- `{result.feature}` (AUC {result.auc:.4f})" for result in audit.features[:5])
    lines.extend(["", "### Features to Drop", ""])
    dropped = [duplicate for _, duplicate in audit.duplicate_pairs]
    weak = [result.feature for result in audit.features if result.auc < audit.config.min_auc]
    for feature in [*dropped, *weak]:
        lines.append(f"- `{feature}`")
    if not dropped and not weak:
        lines.append("- None")
    return "\n".join(lines) + "\n"


def save_report(markdown: str, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(markdown)
