"""Score distribution plotting."""

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
    _HAS_SCIPY_KDE,
    _gaussian_kde,
)


def plot_score_distribution(
    scores: pd.Series,
    labels: pd.Series,
    output_path: str,
    threshold: float | None = None,
    title: str = "Anomaly Score Distribution",
) -> None:
    """Histogram + KDE of anomaly scores separated by red team vs baseline.

    Auto-ranges bins from data min to max (scores can exceed 1.0).
    Uses log scale on y-axis.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    mask_red = labels.fillna(0).astype(int) == 1
    mask_base = ~mask_red

    score_min = scores.min()
    score_max = scores.max()
    bins = np.linspace(score_min, score_max, 50)

    base_scores = scores[mask_base].dropna()
    red_scores = scores[mask_red].dropna()

    ax.hist(
        base_scores, bins=bins, alpha=0.6, color="#2ecc71",
        label="Baseline events", edgecolor="white", linewidth=0.3,
    )
    if red_scores.any():
        ax.hist(
            red_scores, bins=bins, alpha=0.7, color="#e74c3c",
            label="Red team events", edgecolor="white", linewidth=0.3,
        )

    if _HAS_SCIPY_KDE:
        x_kde = np.linspace(score_min, score_max, 500)
        if len(base_scores) > 10:
            try:
                kde_base = _gaussian_kde(base_scores)
                ax.plot(x_kde, kde_base(x_kde) * len(base_scores) * (bins[1] - bins[0]),
                        color="#27ae60", lw=1.5, alpha=0.8)
            except (np.linalg.LinAlgError, ValueError):
                pass
        if len(red_scores) > 10:
            try:
                kde_red = _gaussian_kde(red_scores)
                ax.plot(x_kde, kde_red(x_kde) * len(red_scores) * (bins[1] - bins[0]),
                        color="#c0392b", lw=1.5, alpha=0.8)
            except (np.linalg.LinAlgError, ValueError):
                pass

    if threshold is not None:
        ax.axvline(x=threshold, color="#f39c12", lw=1.5, ls="--", label=f"Threshold ({threshold:.2f})")

    ax.set_yscale("log")
    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_title(
        f"Score range [{score_min:.3f}, {score_max:.3f}]  |  "
        f"Baseline: {len(base_scores):,}  Red team: {len(red_scores):,}",
        fontsize=9, color="#7f8c8d", pad=22,
    )
    ax.set_xlabel("Anomaly Score", fontsize=LABEL_FS)
    ax.set_ylabel("Count (log scale)", fontsize=LABEL_FS)
    ax.legend(fontsize=9, framealpha=0.9)
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    _save_fig(fig, output_path)
