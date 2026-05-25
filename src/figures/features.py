"""Feature-analysis figure generators."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.style import _save_fig, logger, save_placeholder_figure


def plot_feature_audit(audit_data: dict | None, output_dir: Path) -> None:
    if audit_data is None:
        logger.warning("Skipping feature audit figure: audit_data is None")
        save_placeholder_figure(
            str(output_dir / "feature_audit.png"),
            "Feature Audit",
            "audit_data is None",
        )
        return

    rows = []

    features_list = audit_data.get("features") if isinstance(audit_data, dict) else None
    if isinstance(features_list, list):
        for item in features_list:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if name is None:
                name = item.get("feature")
            auc = item.get("auc")
            if name is None or auc is None:
                continue
            rows.append((str(name), float(auc)))
    elif isinstance(audit_data, dict):
        for key, value in audit_data.items():
            if not isinstance(value, dict):
                continue
            auc = value.get("auc")
            if auc is None:
                continue
            rows.append((str(key), float(auc)))

    if not rows:
        logger.warning("Skipping feature audit figure: no feature AUC data found")
        save_placeholder_figure(
            str(output_dir / "feature_audit.png"),
            "Feature Audit",
            "no feature AUC data found",
        )
        return

    df = pd.DataFrame(rows, columns=["feature", "auc"]).sort_values("auc", ascending=True)
    colors = [
        "#4CAF50" if v > 0.7 else "#FF9800" if v >= 0.5 else "#F44336"
        for v in df["auc"].values
    ]

    fig, ax = plt.subplots()
    bars = ax.barh(df["feature"], df["auc"], color=colors, alpha=0.9, edgecolor="white", linewidth=0.5)
    ax.axvline(0.5, linestyle="--", color="gray", linewidth=1)

    for bar, val in zip(bars, df["auc"].values):
        ax.text(
            bar.get_width() + 0.01,
            bar.get_y() + bar.get_height() / 2,
            f"{val:.2f}",
            ha="left",
            va="center",
            fontsize=8,
        )

    ax.set_title("Individual Feature Discriminative Power (AUC)")
    ax.set_xlabel("AUC Score")
    ax.set_ylabel("Feature")
    ax.set_xlim(0, max(1.0, float(df["auc"].max()) + 0.08))
    _save_fig(fig, str(output_dir / "feature_audit.png"))


def plot_ablation(analysis_data: dict | None, output_dir: Path) -> None:
    if analysis_data is None:
        logger.warning("Skipping ablation figure: analysis_data is None")
        save_placeholder_figure(
            str(output_dir / "ablation_study.png"),
            "Ablation Study",
            "analysis_data is None",
        )
        return

    ablation_data = analysis_data.get("tabular_vs_graph_ablation")
    if not isinstance(ablation_data, dict):
        logger.warning("Skipping ablation figure: tabular_vs_graph_ablation not found")
        save_placeholder_figure(
            str(output_dir / "ablation_study.png"),
            "Ablation Study",
            "tabular_vs_graph_ablation not found",
        )
        return

    categories = ["pure_tabular", "graph_derived", "combined"]
    category_aliases = {
        "pure_tabular": {"pure_tabular", "pure_tabular_only", "tabular", "tabular_only"},
        "graph_derived": {"graph_derived", "graph_derived_only", "graph", "graph_only"},
        "combined": {"combined", "all", "all_features"},
    }

    normalized_ablation_data: dict[str, dict] = {}
    if isinstance(ablation_data.get("results"), list):
        for item in ablation_data["results"]:
            if not isinstance(item, dict):
                continue
            name = item.get("name")
            if not isinstance(name, str):
                continue
            lowered = name.lower()
            matched = next(
                (
                    canonical
                    for canonical, aliases in category_aliases.items()
                    if lowered in aliases
                ),
                None,
            )
            if matched is None:
                continue
            normalized_ablation_data[matched] = item
    else:
        for canonical in categories:
            node = ablation_data.get(canonical)
            if isinstance(node, dict):
                normalized_ablation_data[canonical] = node
    metric_candidates = [
        ("eval_auc", "AUC"),
        ("auc", "AUC"),
        ("f1", "F1"),
        ("eval_f1", "F1"),
        ("recall", "Recall"),
        ("eval_recall", "Recall"),
    ]

    metrics = []
    seen_labels = set()
    for key, label in metric_candidates:
        present = any(
            isinstance(normalized_ablation_data.get(cat), dict)
            and normalized_ablation_data.get(cat).get(key) is not None
            for cat in categories
        )
        if present and label not in seen_labels:
            metrics.append((key, label))
            seen_labels.add(label)

    if not metrics:
        logger.warning("Skipping ablation figure: no usable metrics found")
        save_placeholder_figure(
            str(output_dir / "ablation_study.png"),
            "Ablation Study",
            "no usable metrics found",
        )
        return

    values_by_metric = []
    for key, _ in metrics:
        vals = []
        for cat in categories:
            cat_data = normalized_ablation_data.get(cat)
            vals.append(float(cat_data.get(key, 0.0)) if isinstance(cat_data, dict) else 0.0)
        values_by_metric.append(vals)

    fig, ax = plt.subplots()
    x = np.arange(len(categories))
    n_metrics = len(metrics)
    bar_width = 0.8 / n_metrics
    palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0", "#F44336"]

    for i, ((_, label), vals) in enumerate(zip(metrics, values_by_metric)):
        offset = (i - n_metrics / 2 + 0.5) * bar_width
        bars = ax.bar(
            x + offset,
            vals,
            bar_width,
            label=label,
            color=palette[i % len(palette)],
            alpha=0.85,
            edgecolor="white",
            linewidth=0.5,
        )
        for bar, val in zip(bars, vals):
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                bar.get_height() + 0.01,
                f"{val:.2f}",
                ha="center",
                va="bottom",
                fontsize=7,
            )

    ax.set_xticks(x)
    ax.set_xticklabels(["pure_tabular", "graph_derived", "combined"])
    ax.set_ylabel("Score")
    ax.set_xlabel("Feature Category")
    ax.set_ylim(0, 1.15)
    ax.set_title("Feature Category Ablation Study")
    ax.legend(framealpha=0.9)
    _save_fig(fig, str(output_dir / "ablation_study.png"))


def plot_feature_sweep(analysis_data: dict | None, output_dir: Path) -> None:
    if analysis_data is None:
        logger.warning("Skipping feature sweep figure: analysis_data is None")
        save_placeholder_figure(
            str(output_dir / "feature_sweep.png"),
            "Feature Sweep",
            "analysis_data is None",
        )
        return

    sweep_data = analysis_data.get("graph_features_test")
    if not isinstance(sweep_data, dict):
        logger.warning("Skipping feature sweep figure: graph_features_test not found")
        save_placeholder_figure(
            str(output_dir / "feature_sweep.png"),
            "Feature Sweep",
            "graph_features_test not found",
        )
        return

    rows = []
    results_list = sweep_data.get("results")
    if isinstance(results_list, list):
        for item in results_list:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("feature_group") or item.get("group")
            auc = item.get("eval_auc")
            if auc is None:
                auc = item.get("auc")
            if name is None or auc is None:
                continue
            rows.append((str(name), float(auc)))
    else:
        for key, value in sweep_data.items():
            if not isinstance(value, dict):
                continue
            auc = value.get("eval_auc")
            if auc is None:
                auc = value.get("auc")
            if auc is None:
                continue
            rows.append((str(key), float(auc)))

    if not rows:
        logger.warning("Skipping feature sweep figure: no eval_auc/auc entries found")
        save_placeholder_figure(
            str(output_dir / "feature_sweep.png"),
            "Feature Sweep",
            "no eval_auc/auc entries found",
        )
        return

    df = pd.DataFrame(rows, columns=["group", "auc"])

    baseline_auc = None
    for _, row in df.iterrows():
        g = row["group"].lower()
        if g == "base" or "base" in g:
            baseline_auc = float(row["auc"])
            break
    if baseline_auc is None:
        baseline_auc = float(df.iloc[0]["auc"])

    colors = ["#4CAF50" if float(v) > baseline_auc else "#2196F3" for v in df["auc"].values]

    fig, ax = plt.subplots()
    bars = ax.bar(df["group"], df["auc"], color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    ax.axhline(baseline_auc, linestyle="--", color="gray", linewidth=1)

    for bar, val in zip(bars, df["auc"].values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.2f}",
            ha="center",
            va="bottom",
            fontsize=8,
        )

    ax.set_title("Graph Feature Contribution Analysis")
    ax.set_xlabel("Feature Group")
    ax.set_ylabel("Evaluation AUC")
    ax.set_ylim(0, max(1.0, float(df["auc"].max()) + 0.08))
    ax.tick_params(axis="x", rotation=25)
    _save_fig(fig, str(output_dir / "feature_sweep.png"))
