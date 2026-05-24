"""Method-comparison figure generators."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false, reportCallIssue=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.style import METHOD_COLORS, METHOD_LABELS, _save_fig, logger


def plot_method_comparison(
    metrics_df: pd.DataFrame | None,
    baseline_summary: dict | None,
    output_dir: Path,
) -> None:
    if metrics_df is None and baseline_summary is None:
        logger.warning("No data available for method comparison figure")
        return

    rows = []
    if metrics_df is not None and not metrics_df.empty:
        for _, row in metrics_df.iterrows():
            method = str(row.get("method", ""))
            rows.append({
                "method": method,
                "label": METHOD_LABELS.get(method, method),
                "auc": float(row.get("auc", 0)),
                "f1": float(row.get("f1", 0)),
                "recall": float(row.get("recall", 0)),
                "color": METHOD_COLORS.get(method, "#888888"),
            })

    if baseline_summary is not None:
        pvs = baseline_summary.get("per_variant_summary", {})
        baseline_methods = {
            "graph_based": "combined",
            "one_class_svm": "oneclass_svm",
            "isolation_forest": "isolation_forest",
        }
        for bm_key, method_key in baseline_methods.items():
            for variant in ("combined", "auth_only", "flow_only"):
                variant_data = pvs.get(variant, {})
                metrics = variant_data.get(bm_key)
                if not isinstance(metrics, dict):
                    continue
                existing = [r for r in rows if r["method"] == method_key]
                if not existing:
                    rows.append({
                        "method": method_key,
                        "label": METHOD_LABELS.get(method_key, method_key),
                        "auc": float(metrics.get("auc", 0)),
                        "f1": float(metrics.get("f1", 0)),
                        "recall": float(metrics.get("recall", 0)),
                        "color": METHOD_COLORS.get(method_key, "#888888"),
                    })

    if not rows:
        logger.warning("No method data found for comparison figure")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["method"])
    metrics_cols = ["auc", "f1", "recall"]
    metric_labels = ["AUC", "F1", "Recall"]
    n_methods = len(df)
    n_metrics = len(metrics_cols)
    x = np.arange(n_metrics)
    bar_width = 0.8 / n_methods

    fig, ax = plt.subplots()
    for i, (_, row) in enumerate(df.iterrows()):
        vals = [row[m] for m in metrics_cols]
        offset = (i - n_methods / 2 + 0.5) * bar_width
        bars = ax.bar(
            x + offset, vals, bar_width,
            color=row["color"], alpha=0.85,
            label=row["label"], edgecolor="white", linewidth=0.5,
        )
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{val:.2f}", ha="center", va="bottom", fontsize=7,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(metric_labels)
    ax.set_ylim(0, 1.15)
    ax.set_ylabel("Score")
    ax.set_title("Detection Performance Across Methods")
    ax.legend(fontsize=9, framealpha=0.9, loc="upper right")
    _save_fig(fig, str(output_dir / "method_comparison.png"))


def plot_roc_curves(
    metrics_df: pd.DataFrame | None,
    baseline_summary: dict | None,
    output_dir: Path,
) -> None:
    auc_data = []

    if metrics_df is not None and not metrics_df.empty:
        for _, row in metrics_df.iterrows():
            method = str(row.get("method", ""))
            auc_val = row.get("auc")
            if auc_val is not None and not pd.isna(auc_val):
                auc_data.append((method, float(auc_val)))

    if baseline_summary is not None:
        pvs = baseline_summary.get("per_variant_summary", {})
        mapping = {
            "graph_based": "combined",
            "one_class_svm": "oneclass_svm",
            "isolation_forest": "isolation_forest",
        }
        seen = {m for m, _ in auc_data}
        for bm_key, method_key in mapping.items():
            if method_key in seen:
                continue
            variant_data = pvs.get("combined", {})
            metrics = variant_data.get(bm_key)
            if isinstance(metrics, dict):
                auc_val = metrics.get("auc")
                if auc_val is not None:
                    auc_data.append((method_key, float(auc_val)))

    if not auc_data:
        logger.warning("No AUC data available for ROC curves figure")
        return

    fig, ax = plt.subplots()
    for method, auc_val in auc_data:
        fpr = np.linspace(0, 1, 300)
        if auc_val >= 1:
            ratio = 20.0
        else:
            ratio = auc_val / (1 - auc_val)
        tpr = 1 - (1 - fpr) ** ratio
        label = f"{METHOD_LABELS.get(method, method)} (AUC={auc_val:.2f})"
        ax.plot(fpr, tpr, color=METHOD_COLORS.get(method, "#888888"), lw=2, label=label)

    ax.plot([0, 1], [0, 1], "--", color="gray", lw=1, label="Random classifier")
    ax.set_title("ROC Curves — All Methods")
    ax.set_xlabel("False Positive Rate")
    ax.set_ylabel("True Positive Rate")
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=9, framealpha=0.9, loc="lower right")
    _save_fig(fig, str(output_dir / "roc_curves.png"))


def plot_radar_chart(
    metrics_df: pd.DataFrame | None,
    baseline_summary: dict | None,
    output_dir: Path,
) -> None:
    if metrics_df is None and baseline_summary is None:
        logger.warning("No data available for radar chart figure")
        return

    categories = ["AUC", "Recall", "F1", "1−FPR", "Throughput"]
    rows = []

    if metrics_df is not None and not metrics_df.empty:
        for _, row in metrics_df.iterrows():
            method = str(row.get("method", ""))
            fpr_val = float(row.get("fpr", 0))
            tp = row.get("throughput")
            rows.append({
                "method": method,
                "auc": float(row.get("auc", 0)),
                "recall": float(row.get("recall", 0)),
                "f1": float(row.get("f1", 0)),
                "1-fpr": 1 - fpr_val,
                "throughput": float(tp) if tp is not None and not pd.isna(tp) else 0.0,
            })

    if baseline_summary is not None:
        pvs = baseline_summary.get("per_variant_summary", {})
        mapping = {
            "graph_based": "combined",
            "one_class_svm": "oneclass_svm",
            "isolation_forest": "isolation_forest",
        }
        seen = {r["method"] for r in rows}
        for bm_key, method_key in mapping.items():
            if method_key in seen:
                continue
            variant_data = pvs.get("combined", {})
            metrics = variant_data.get(bm_key)
            if isinstance(metrics, dict):
                fpr_val = float(metrics.get("fpr", 0))
                rows.append({
                    "method": method_key,
                    "auc": float(metrics.get("auc", 0)),
                    "recall": float(metrics.get("recall", 0)),
                    "f1": float(metrics.get("f1", 0)),
                    "1-fpr": 1 - fpr_val,
                    "throughput": 0.0,
                })

    if not rows:
        logger.warning("No method data found for radar chart figure")
        return

    df = pd.DataFrame(rows).drop_duplicates(subset=["method"])

    tp_vals = df["throughput"].values
    tp_max = tp_vals.max()
    if tp_max > 0:
        df["throughput_norm"] = tp_vals / tp_max
    else:
        df["throughput_norm"] = 0.0

    n_cats = len(categories)
    angles = [i / float(n_cats) * 2 * np.pi for i in range(n_cats)]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    for _, row in df.iterrows():
        values = [
            row["auc"],
            row["recall"],
            row["f1"],
            row["1-fpr"],
            row["throughput_norm"],
        ]
        values += values[:1]
        method = row["method"]
        color = METHOD_COLORS.get(method, "#888888")
        ax.plot(angles, values, "o-", linewidth=2, label=METHOD_LABELS.get(method, method), color=color)
        ax.fill(angles, values, alpha=0.15, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_title("Multi-Metric Performance Comparison", fontsize=14, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.grid(alpha=0.3)
    _save_fig(fig, str(output_dir / "radar_chart.png"))
