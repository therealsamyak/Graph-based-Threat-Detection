"""Method-comparison figure generators (3×3 method×variant data model)."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.style import (
    METHOD_ORDER,
    VARIANT_LABELS,
    VARIANT_ORDER,
    _save_fig,
    get_method_color,
    get_method_label,
    logger,
)


def plot_method_comparison(
    matrix: pd.DataFrame | None,
    output_dir: Path,
) -> None:
    """Grouped-bar chart: 3 subplots (AUC, F1, Recall) × 3 variant groups × 3 methods."""
    if matrix is None or matrix.empty:
        logger.warning("No data available for method comparison figure")
        return

    metrics_cols = ["auc", "f1", "recall"]
    metric_labels = ["AUC", "F1", "Recall"]
    n_variants = len(VARIANT_ORDER)
    n_methods = len(METHOD_ORDER)
    bar_width = 0.22

    fig, axes = plt.subplots(1, 3, figsize=(16, 5), sharey=True)

    for ax, col, label in zip(axes, metrics_cols, metric_labels):
        x = np.arange(n_variants)

        for j, method in enumerate(METHOD_ORDER):
            vals = []
            for variant in VARIANT_ORDER:
                row = matrix[(matrix["method"] == method) & (matrix["variant"] == variant)]
                vals.append(float(row[col].iloc[0]) if not row.empty else 0.0)

            offset = (j - n_methods / 2 + 0.5) * bar_width
            colors = [get_method_color(method, v) for v in VARIANT_ORDER]
            bars = ax.bar(
                x + offset, vals, bar_width,
                color=colors, alpha=0.85,
                label=method.replace("_", " ").title(),
                edgecolor="white", linewidth=0.5,
            )
            for bar, val in zip(bars, vals):
                ax.text(
                    bar.get_x() + bar.get_width() / 2,
                    bar.get_height() + 0.01,
                    f"{val:.2f}", ha="center", va="bottom", fontsize=7,
                )

        ax.set_xticks(x)
        ax.set_xticklabels([VARIANT_LABELS[v] for v in VARIANT_ORDER])
        ax.set_ylim(0, 1.15)
        ax.set_ylabel("Score")
        ax.set_title(label)
        ax.legend(fontsize=8, framealpha=0.9, loc="upper right")

    fig.suptitle("Detection Performance Across Methods", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save_fig(fig, str(output_dir / "method_comparison.png"))


def plot_roc_curves(
    matrix: pd.DataFrame | None,
    roc_data: dict | None,
    output_dir: Path,
) -> None:
    """ROC curves: 3 panels (one per variant), real curves for SVM/IF, synthetic for graph_based."""
    if matrix is None or matrix.empty:
        logger.warning("No data available for ROC curves figure")
        return

    if roc_data is None:
        roc_data = {}

    fig, axes = plt.subplots(1, 3, figsize=(18, 5))

    for ax, variant in zip(axes, VARIANT_ORDER):
        variant_label = VARIANT_LABELS[variant]

        for method in METHOD_ORDER:
            row = matrix[(matrix["method"] == method) & (matrix["variant"] == variant)]
            if row.empty:
                continue
            auc_val = float(row["auc"].iloc[0])
            color = get_method_color(method, variant)
            label = f"{get_method_label(method, variant)} (AUC={auc_val:.2f})"

            if method in ("one_class_svm", "isolation_forest") and (method, variant) in roc_data:
                fpr, tpr = roc_data[(method, variant)]
                ax.plot(fpr, tpr, color=color, lw=2, label=label)
            else:
                # Synthetic ROC from AUC for graph_based
                fpr = np.linspace(0, 1, 300)
                ratio = auc_val / (1 - auc_val) if auc_val < 1 else 20.0
                tpr = 1 - (1 - fpr) ** ratio
                ax.plot(fpr, tpr, color=color, lw=2, label=label, linestyle="--")

        ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="Random classifier")
        ax.set_title(f"ROC — {variant_label}")
        ax.set_xlabel("False Positive Rate")
        ax.set_ylabel("True Positive Rate")
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        ax.legend(fontsize=7, framealpha=0.9, loc="lower right")
        ax.grid(alpha=0.3)

    fig.suptitle("ROC Curves — All Methods × Variants", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    _save_fig(fig, str(output_dir / "roc_curves.png"))


def plot_radar_chart(
    matrix: pd.DataFrame | None,
    output_dir: Path,
) -> None:
    """Radar charts: 3 panels (one per variant), 5-axis radar with all 3 methods overlaid."""
    if matrix is None or matrix.empty:
        logger.warning("No data available for radar chart figure")
        return

    # Normalize throughput across entire matrix
    matrix = matrix.copy()
    tp_max = float(matrix["throughput"].max())
    if tp_max > 0:
        matrix["throughput_norm"] = matrix["throughput"] / tp_max
    else:
        matrix["throughput_norm"] = 0.0

    categories = ["AUC", "Recall", "F1", "1−FPR", "Throughput"]
    n_cats = len(categories)
    angles = [i / float(n_cats) * 2 * np.pi for i in range(n_cats)]
    angles_closed = angles + angles[:1]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6), subplot_kw={"projection": "polar"})

    for ax, variant in zip(axes, VARIANT_ORDER):
        variant_label = VARIANT_LABELS[variant]

        for method in METHOD_ORDER:
            row = matrix[(matrix["method"] == method) & (matrix["variant"] == variant)]
            if row.empty:
                continue
            r = row.iloc[0]
            fpr_val = float(r.get("fpr", 0))
            tp_norm = float(r.get("throughput_norm", 0))
            values = [
                float(r.get("auc", 0)),
                float(r.get("recall", 0)),
                float(r.get("f1", 0)),
                1 - fpr_val,
                tp_norm,
            ]
            values_closed = values + values[:1]
            color = get_method_color(method, variant)
            label = get_method_label(method, variant)
            ax.plot(angles_closed, values_closed, "o-", linewidth=2, label=label, color=color)
            ax.fill(angles_closed, values_closed, alpha=0.15, color=color)

        ax.set_xticks(angles)
        ax.set_xticklabels(categories, fontsize=9)
        ax.set_ylim(0, 1)
        ax.set_title(f"{variant_label}", fontsize=12, fontweight="bold", pad=20)
        ax.legend(loc="upper right", bbox_to_anchor=(1.35, 1.1), fontsize=7)
        ax.grid(alpha=0.3)

    fig.suptitle("Multi-Metric Performance Comparison", fontsize=14, fontweight="bold")
    fig.tight_layout(rect=[0, 0, 1, 0.93])
    _save_fig(fig, str(output_dir / "radar_chart.png"))
