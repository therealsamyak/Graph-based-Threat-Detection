"""ROC curve plotting."""

from __future__ import annotations

import numpy as np
import matplotlib.pyplot as plt

from src.visualization.style import (
    _apply_style,
    _save_fig,
    PALETTE,
    LINE_STYLES,
    BG_COLOR,
    FIG_SIZE,
    DPI,
    TITLE_FS,
    LABEL_FS,
)


def plot_roc_curves(
    results_list: list[dict],
    output_path: str,
    title: str = "ROC Curves — Lateral Movement Detection",
) -> None:
    """Overlaid ROC curves for multiple detection methods.

    Each dict should have 'method_name' (str), 'auc' (float), and
    optionally 'fpr_array'/'tpr_array' for empirically measured curves.
    When arrays are missing or too short, a smooth curve is synthesized
    from the AUC value.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    if not results_list:
        ax.text(0.5, 0.5, "No results to display", ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color="#95a5a6")
        ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
        _save_fig(fig, output_path)
        return

    for idx, res in enumerate(results_list):
        color = PALETTE[idx % len(PALETTE)]
        ls = LINE_STYLES[idx % len(LINE_STYLES)]
        name = res.get("method_name", f"Method {idx + 1}")
        auc_val = res.get("auc", 0.0)

        fpr_arr = res.get("fpr_array")
        tpr_arr = res.get("tpr_array")

        if (fpr_arr is not None and tpr_arr is not None
                and hasattr(fpr_arr, "__len__") and len(fpr_arr) > 3):
            fpr = np.asarray(fpr_arr, dtype=float)
            tpr = np.asarray(tpr_arr, dtype=float)
        else:
            fpr = np.linspace(0, 1, 300)
            ratio = auc_val / (1 - auc_val + 1e-9)
            tpr = 1 - (1 - fpr) ** ratio

        label = f"{name} (AUC = {auc_val:.3f})" if auc_val > 0 else name
        ax.plot(fpr, tpr, color=color, lw=2, ls=ls, label=label)

    ax.plot([0, 1], [0, 1], "--", color="#95a5a6", lw=1, label="Random baseline")

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_title("Comparison of detection methods by true vs false positive rate",
                 fontsize=9, color="#7f8c8d", pad=22)
    ax.set_xlabel("False Positive Rate", fontsize=LABEL_FS)
    ax.set_ylabel("True Positive Rate", fontsize=LABEL_FS)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9, framealpha=0.9, loc="lower right")
    ax.tick_params(labelsize=9)
    ax.set_aspect("equal", adjustable="box")
    fig.tight_layout()
    _save_fig(fig, output_path)
