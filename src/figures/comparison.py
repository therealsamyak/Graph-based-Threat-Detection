"""Cross-method comparison figure generators."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.style import (
    BASE_METHOD_COLORS,
    METHOD_ORDER,
    VARIANT_LABELS,
    VARIANT_ORDER,
    _save_fig,
    get_method_label,
    logger,
)

# Display names for y-axis of heatmap
_METHOD_DISPLAY = {
    "graph_based": "Graph",
    "one_class_svm": "SVM",
    "isolation_forest": "Isolation Forest",
}

# Variant markers for scatter
_VARIANT_MARKERS = {
    "combined": "o",
    "auth_only": "s",
    "flow_only": "^",
}


# ---------------------------------------------------------------------------
# 1. Variant heatmap
# ---------------------------------------------------------------------------
def plot_variant_heatmap(matrix: pd.DataFrame, output_dir: Path) -> None:
    """3×3 heatmaps for AUC, F1, Recall across method×variant (separate PNGs)."""
    if matrix is None or matrix.empty:
        logger.warning("plot_variant_heatmap: empty matrix, skipping")
        return

    metrics = ["auc", "f1", "recall"]
    titles = [
        "AUC Across Method×Variant",
        "F1 Across Method×Variant",
        "Recall Across Method×Variant",
    ]

    for metric, title in zip(metrics, titles):
        data = np.full((len(METHOD_ORDER), len(VARIANT_ORDER)), np.nan)
        for i, method in enumerate(METHOD_ORDER):
            for j, variant in enumerate(VARIANT_ORDER):
                row = matrix[
                    (matrix["method"] == method) & (matrix["variant"] == variant)
                ]
                if not row.empty:
                    val = row[metric].iloc[0]
                    if val is not None and not pd.isna(val):
                        data[i, j] = float(val)

        fig, ax = plt.subplots(figsize=(8, 5))
        im = ax.imshow(data, cmap=plt.cm.RdYlGn, vmin=0, vmax=1, aspect="auto")
        for spine in ax.spines.values():
            spine.set_visible(False)
        ax.tick_params(axis="both", which="both", length=0)
        ax.grid(False)
        ax.xaxis.grid(False)
        ax.yaxis.grid(False)
        for line in ax.get_xgridlines() + ax.get_ygridlines():
            line.set_visible(False)
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

        ax.set_xticks(range(len(VARIANT_ORDER)))
        ax.set_xticklabels([VARIANT_LABELS[v] for v in VARIANT_ORDER])
        ax.set_yticks(range(len(METHOD_ORDER)))
        ax.set_yticklabels([_METHOD_DISPLAY[m] for m in METHOD_ORDER])
        ax.set_title(title)

        # Annotate cells
        for i in range(data.shape[0]):
            for j in range(data.shape[1]):
                val = data[i, j]
                if not np.isnan(val):
                    ax.text(
                        j, i, f"{val:.3f}",
                        ha="center", va="center",
                        fontsize=9,
                        color="white" if val < 0.4 else "black",
                    )

        fig.tight_layout()
        _save_fig(fig, str(output_dir / f"variant_heatmap_{metric}.png"))
        plt.close(fig)
        logger.info(f"Saved variant_heatmap_{metric}.png")


# ---------------------------------------------------------------------------
# 2. Detection counts
# ---------------------------------------------------------------------------
def plot_detection_counts(matrix: pd.DataFrame, output_dir: Path) -> None:
    """Grouped bar chart: detected vs redteam counts per method×variant."""
    if matrix is None or matrix.empty:
        logger.warning("plot_detection_counts: empty matrix, skipping")
        return

    combos: list[tuple[str, str]] = []
    detected: list[float] = []
    redteam: list[float] = []

    for variant in VARIANT_ORDER:
        for method in METHOD_ORDER:
            row = matrix[
                (matrix["method"] == method) & (matrix["variant"] == variant)
            ]
            if row.empty:
                continue
            r = row.iloc[0]
            d = r.get("num_detected_pairs")
            rt = r.get("num_redteam_pairs")
            if pd.isna(d) or d is None:
                d = 0
            if pd.isna(rt) or rt is None:
                rt = 0
            combos.append((method, variant))
            detected.append(float(d))
            redteam.append(float(rt))

    if not combos:
        logger.warning("plot_detection_counts: no valid combos found")
        return

    n = len(combos)
    x = np.arange(n)
    width = 0.35

    fig, ax = plt.subplots(figsize=(14, 6))
    _bars_d = ax.bar(x - width / 2, detected, width, label="Detected", color="#9C27B0")
    _bars_r = ax.bar(x + width / 2, redteam, width, label="Red Team", color="#F44336")

    # Ratio annotations
    for i in range(n):
        rt = redteam[i]
        d = detected[i]
        if rt > 0:
            ratio = d / rt
            ax.annotate(
                f"{ratio:.2f}",
                (x[i], max(d, rt) + 0.5),
                ha="center", va="bottom", fontsize=8,
            )

    labels = [get_method_label(m, v) for m, v in combos]
    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_ylabel("Count")
    ax.set_title("Detection Counts: Predicted vs Ground Truth")
    ax.legend(loc="upper left", bbox_to_anchor=(1.02, 1))

    fig.tight_layout()
    _save_fig(fig, str(output_dir / "detection_counts.png"))
    logger.info("Saved detection_counts.png")


# ---------------------------------------------------------------------------
# 3. Performance tradeoff scatter
# ---------------------------------------------------------------------------
def plot_performance_tradeoff(matrix: pd.DataFrame, output_dir: Path) -> None:
    """Scatter: latency vs AUC, colored by method, shaped by variant."""
    if matrix is None or matrix.empty:
        logger.warning("plot_performance_tradeoff: empty matrix, skipping")
        return

    fig, ax = plt.subplots(figsize=(10, 7))

    plotted_labels: set[str] = set()
    handles: list = []
    labels: list[str] = []

    for variant in VARIANT_ORDER:
        marker = _VARIANT_MARKERS[variant]
        for method in METHOD_ORDER:
            row = matrix[
                (matrix["method"] == method) & (matrix["variant"] == variant)
            ]
            if row.empty:
                continue
            r = row.iloc[0]
            latency = r.get("latency")
            auc = r.get("auc")
            if latency is None or pd.isna(latency) or auc is None or pd.isna(auc):
                continue

            # Convert to ms if needed (assume seconds if > 1)
            lat_ms = float(latency)
            if lat_ms > 1:
                lat_ms *= 1000

            color = BASE_METHOD_COLORS[method]
            method_label = _METHOD_DISPLAY[method]
            variant_label = VARIANT_LABELS[variant]
            combo_label = f"{method_label} ({variant_label})"

            sc = ax.scatter(lat_ms, float(auc), color=color, marker=marker, s=120, zorder=5)

            if combo_label not in plotted_labels:
                handles.append(sc)
                labels.append(combo_label)
                plotted_labels.add(combo_label)

            ax.annotate(
                combo_label,
                (lat_ms, float(auc)),
                textcoords="offset points",
                xytext=(8, 6),
                fontsize=7,
                alpha=0.85,
            )

    if not handles:
        logger.warning("plot_performance_tradeoff: no data points to plot, skipping")
        plt.close(fig)
        return

    ax.legend(handles, labels, loc="upper left", bbox_to_anchor=(1.02, 1), fontsize=8, framealpha=0.9)
    ax.set_xlabel("Latency (ms)")
    ax.set_ylabel("AUC")
    ax.set_title("Accuracy vs Speed Tradeoff")

    # Ideal zone annotation
    ax.annotate(
        "Ideal",
        xy=(0.02, 0.98),
        xycoords="axes fraction",
        fontsize=10,
        fontstyle="italic",
        color="green",
        ha="left",
        va="top",
    )

    fig.tight_layout()
    _save_fig(fig, str(output_dir / "performance_tradeoff.png"))
    logger.info("Saved performance_tradeoff.png")


# ---------------------------------------------------------------------------
# 4. Metrics summary table
# ---------------------------------------------------------------------------
def plot_metrics_summary(matrix: pd.DataFrame, output_dir: Path) -> None:
    """Table figure with all 9 rows and key metric columns."""
    if matrix is None or matrix.empty:
        logger.warning("plot_metrics_summary: empty matrix, skipping")
        return

    metric_cols = ["auc", "f1", "recall", "fpr", "precision"]
    headers = ["Method", "Variant", "AUC", "F1", "Recall", "FPR", "Precision"]

    # Sort by variant then method
    sorted_df = matrix.sort_values(["variant", "method"]).reset_index(drop=True)

    cell_text: list[list[str]] = []
    for _, row in sorted_df.iterrows():
        method_label = _METHOD_DISPLAY.get(row["method"], str(row["method"]))
        variant_label = VARIANT_LABELS.get(row["variant"], str(row["variant"]))
        line = [method_label, variant_label]
        for col in metric_cols:
            val = row.get(col)
            if val is not None and not pd.isna(val):
                line.append(f"{float(val):.3f}")
            else:
                line.append("—")
        cell_text.append(line)

    # Find best index per metric column (skip Method=0, Variant=1)
    col_offsets = {m: i + 2 for i, m in enumerate(metric_cols)}  # col index in cell_text row
    best_idx: dict[int, int] = {}
    for col_name, col_idx in col_offsets.items():
        best_val = -1.0
        best_row = -1
        for r, row in enumerate(sorted_df.iterrows()):
            val = row[1].get(col_name)
            if val is not None and not pd.isna(val):
                fval = float(val)
                # For FPR, lower is better
                if col_name == "fpr":
                    if best_row == -1 or fval < best_val:
                        best_val = fval
                        best_row = r
                else:
                    if fval > best_val:
                        best_val = fval
                        best_row = r
        if best_row >= 0:
            best_idx[col_idx] = best_row

    fig, ax = plt.subplots(figsize=(12, 3))
    ax.axis("off")

    col_widths = [0.15, 0.12, 0.1, 0.1, 0.1, 0.1, 0.1]

    table = ax.table(
        cellText=cell_text,
        colLabels=headers,
        loc="center",
        colWidths=col_widths,
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.0, 1.4)

    # Style header
    for j in range(len(headers)):
        cell = table[0, j]
        cell.set_facecolor("#404040")
        cell.set_text_props(color="white", fontweight="bold")

    # Highlight best values
    for col_idx, row_idx in best_idx.items():
        cell = table[row_idx + 1, col_idx]  # +1 for header row
        cell.set_facecolor("#c8e6c9")  # light green
        cell.set_text_props(fontweight="bold")

    ax.set_title("Performance Metrics Summary", fontsize=14, pad=20)

    fig.tight_layout()
    _save_fig(fig, str(output_dir / "metrics_summary.png"))
    logger.info("Saved metrics_summary.png")
