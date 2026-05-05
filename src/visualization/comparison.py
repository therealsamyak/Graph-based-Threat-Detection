"""Method comparison bar chart plotting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.visualization.style import (
    _apply_style,
    _save_fig,
    BG_COLOR,
    FIG_SIZE,
    TITLE_FS,
    LABEL_FS,
)


def plot_method_comparison(
    results_list: list[dict],
    output_path: str,
    title: str = "Method Comparison",
) -> None:
    """Grouped bar chart comparing AUC, Recall, and F1 across methods.

    Groups by dataset (side-by-side subplots). Annotates values on bars.
    """
    _apply_style()

    if not results_list:
        fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)
        ax.text(0.5, 0.5, "No results to display", ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color="#95a5a6")
        ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
        _save_fig(fig, output_path)
        return

    df = pd.DataFrame(results_list)

    if "dataset" in df.columns:
        datasets = sorted(df["dataset"].dropna().unique())
    else:
        datasets = ["All"]

    n_datasets = len(datasets)
    fig, axes = plt.subplots(1, n_datasets, figsize=(5 * n_datasets + 1, 6), facecolor=BG_COLOR)
    if n_datasets == 1:
        axes = [axes]

    metrics = ["auc", "recall", "f1"]
    metric_labels = ["AUC", "Recall", "F1"]
    metric_colors = ["#3498db", "#2ecc71", "#9b59b6"]

    for ax_idx, dataset in enumerate(datasets):
        ax = axes[ax_idx]
        sub = df[df["dataset"] == dataset] if "dataset" in df.columns else df

        if sub.empty:
            ax.text(0.5, 0.5, f"No data for {dataset}", ha="center", va="center",
                    transform=ax.transAxes, fontsize=11, color="#95a5a6")
            ax.set_title(dataset, fontsize=TITLE_FS, fontweight="bold")
            continue

        methods = sub["method"].tolist() if "method" in sub.columns else [f"M{i}" for i in range(len(sub))]
        n_methods = len(methods)
        n_metrics = len(metrics)

        x = np.arange(n_methods)
        bar_width = 0.8 / n_metrics

        for m_idx, (metric, m_label, m_color) in enumerate(zip(metrics, metric_labels, metric_colors)):
            if metric not in sub.columns:
                continue
            vals = sub[metric].fillna(0).values
            offset = (m_idx - n_metrics / 2 + 0.5) * bar_width
            bars = ax.bar(x + offset, vals, bar_width, color=m_color, alpha=0.85,
                          label=m_label, edgecolor="white", linewidth=0.5)

            for bar, val in zip(bars, vals):
                if val > 0:
                    ax.text(
                        bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                        f"{val:.3f}", ha="center", va="bottom", fontsize=7, color="#2c3e50",
                    )

        ax.set_xticks(x)
        ax.set_xticklabels(methods, rotation=25, ha="right", fontsize=8)
        ax.set_ylim(0, 1.15)
        ax.set_ylabel("Score", fontsize=LABEL_FS)
        ax.set_title(dataset, fontsize=TITLE_FS, fontweight="bold", pad=10)
        ax.legend(fontsize=8, framealpha=0.9, loc="upper right")
        ax.tick_params(labelsize=8)

    fig.suptitle(title, fontsize=TITLE_FS + 1, fontweight="bold", y=1.02)
    fig.tight_layout()
    _save_fig(fig, output_path)
