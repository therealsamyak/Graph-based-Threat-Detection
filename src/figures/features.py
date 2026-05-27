"""Feature-analysis figure generators."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false, reportOptionalMemberAccess=false, reportAttributeAccessIssue=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from src.figures.style import _save_fig, logger, save_placeholder_figure


def _per_variant_data(data: dict | None, preferred_key: str | None = None) -> dict[str, dict]:
    if not isinstance(data, dict):
        return {}
    per_variant = data.get("per_variant")
    if isinstance(per_variant, dict):
        out: dict[str, dict] = {}
        for variant, variant_data in per_variant.items():
            if not isinstance(variant_data, dict):
                continue
            if preferred_key is None:
                out[str(variant)] = variant_data
            else:
                nested = variant_data.get(preferred_key)
                if isinstance(nested, dict):
                    out[str(variant)] = nested
        if out:
            return out
    if preferred_key is not None:
        nested = data.get(preferred_key)
        if isinstance(nested, dict):
            return {"combined": nested}
    return {"combined": data}


def _feature_auc_rows(audit_data: dict) -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    features_list = audit_data.get("features")
    if isinstance(features_list, list):
        for item in features_list:
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("feature")
            auc = item.get("auc")
            if name is None or auc is None:
                continue
            rows.append((str(name), float(auc)))
    else:
        for key, value in audit_data.items():
            if not isinstance(value, dict):
                continue
            auc = value.get("auc")
            if auc is not None:
                rows.append((str(key), float(auc)))
    return rows


def plot_feature_audit(audit_data: dict | None, output_dir: Path) -> None:
    variants = _per_variant_data(audit_data)
    rows_by_variant = {}
    for variant, data in variants.items():
        all_rows = sorted(_feature_auc_rows(data), key=lambda row: row[1], reverse=True)
        n = len(all_rows)
        if n <= 10:
            selected = all_rows
        else:
            selected = all_rows[:5] + all_rows[n // 2 - 1 : n // 2 + 1] + all_rows[-3:]
        rows_by_variant[variant] = selected
    rows_by_variant = {variant: rows for variant, rows in rows_by_variant.items() if rows}

    if not rows_by_variant:
        logger.warning("Skipping feature audit figure: no feature AUC data found")
        save_placeholder_figure(
            str(output_dir / "feature_audit.png"),
            "Feature Audit",
            "no feature AUC data found",
        )
        return

    ordered_variants = [v for v in ("combined", "auth_only", "flow_only") if v in rows_by_variant]
    ordered_variants.extend(v for v in rows_by_variant if v not in ordered_variants)

    for variant in ordered_variants:
        fig, ax = plt.subplots(figsize=(8, 6))
        df = pd.DataFrame(rows_by_variant[variant], columns=["feature", "auc"]).sort_values("auc", ascending=True)
        colors = ["#4CAF50" if v > 0.7 else "#FF9800" if v >= 0.5 else "#F44336" for v in df["auc"].values]
        bars = ax.barh(df["feature"], df["auc"], color=colors, alpha=0.9, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, df["auc"].values):
            ax.text(bar.get_width() + 0.01, bar.get_y() + bar.get_height() / 2, f"{val:.2f}", ha="left", va="center", fontsize=8)
        ax.set_title(f"Feature Audit — {variant.replace('_', ' ').title()}")
        ax.set_xlabel("AUC Score")
        ax.set_ylabel("Feature")
        ax.set_xlim(0, max(1.0, float(df["auc"].max()) + 0.08))
        legend_handles = [
            mpatches.Patch(color="#4CAF50", label="Strong feature (AUC > 0.70)"),
            mpatches.Patch(color="#FF9800", label="Weak feature (0.50-0.70)"),
            mpatches.Patch(color="#F44336", label="Below random (AUC < 0.50)"),
        ]
        ax.legend(handles=legend_handles, fontsize=7, framealpha=0.9, loc="upper left", bbox_to_anchor=(1.02, 1))
        fig.tight_layout()
        _save_fig(fig, str(output_dir / f"feature_audit_{variant}.png"))
        plt.close(fig)


def _analysis_result_rows(result_data: dict) -> list[dict]:
    results = result_data.get("results")
    if isinstance(results, list):
        return [item for item in results if isinstance(item, dict)]
    rows = []
    for key, value in result_data.items():
        if isinstance(value, dict):
            item = dict(value)
            item.setdefault("name", key)
            rows.append(item)
    return rows


def plot_ablation(analysis_data: dict | None, output_dir: Path) -> None:
    variants = _per_variant_data(analysis_data, "tabular_vs_graph_ablation")
    if not variants:
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

    auc_by_variant: dict[str, list[float]] = {}
    for variant, ablation_data in variants.items():
        normalized: dict[str, dict] = {}
        for item in _analysis_result_rows(ablation_data):
            name = item.get("name")
            if not isinstance(name, str):
                continue
            lowered = name.lower()
            matched = next((canonical for canonical, aliases in category_aliases.items() if lowered in aliases), None)
            if matched is not None:
                normalized[matched] = item
        vals = []
        for category in categories:
            item = normalized.get(category, {})
            auc = item.get("eval_auc", item.get("auc"))
            vals.append(float(auc) if auc is not None else 0.0)
        if any(vals):
            auc_by_variant[variant] = vals

    if not auc_by_variant:
        logger.warning("Skipping ablation figure: no usable metrics found")
        save_placeholder_figure(
            str(output_dir / "ablation_study.png"),
            "Ablation Study",
            "no usable metrics found",
        )
        return

    ordered_variants = [v for v in ("combined", "auth_only", "flow_only") if v in auc_by_variant]
    ordered_variants.extend(v for v in auc_by_variant if v not in ordered_variants)
    x = np.arange(len(categories))
    width = 0.8 / len(ordered_variants)
    palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0"]

    fig, ax = plt.subplots(figsize=(10, 6))
    for idx, variant in enumerate(ordered_variants):
        vals = auc_by_variant[variant]
        offset = (idx - len(ordered_variants) / 2 + 0.5) * width
        bars = ax.bar(x + offset, vals, width, label=variant.replace("_", " ").title(), color=palette[idx % len(palette)], alpha=0.85, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, vals):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01, f"{val:.2f}", ha="center", va="bottom", fontsize=7)

    ax.set_xticks(x)
    ax.set_xticklabels(["Pure Tabular", "Graph Derived", "Combined"])
    ax.set_ylabel("Holdout Evaluation AUC")
    ax.set_xlabel("Feature Set")
    ax.set_ylim(0, 1.15)
    ax.set_title("Feature Category Ablation Study")
    ax.legend(framealpha=0.9, loc="upper left", bbox_to_anchor=(1.02, 1))
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "ablation_study.png"))


def plot_feature_sweep(analysis_data: dict | None, output_dir: Path) -> None:
    variants = _per_variant_data(analysis_data, "graph_features_test")
    rows_by_variant: dict[str, list[tuple[str, float]]] = {}
    for variant, sweep_data in variants.items():
        rows = []
        for item in _analysis_result_rows(sweep_data):
            name = item.get("name") or item.get("feature_group") or item.get("group")
            auc = item.get("eval_auc", item.get("auc"))
            if name is not None and auc is not None:
                label = str(name).removeprefix("base_plus_").replace("base_", "base ").replace("_", " ")
                rows.append((label, float(auc)))
        if rows:
            rows_by_variant[variant] = rows

    if not rows_by_variant:
        logger.warning("Skipping feature sweep figure: no eval_auc/auc entries found")
        save_placeholder_figure(
            str(output_dir / "feature_sweep.png"),
            "Feature Sweep",
            "no eval_auc/auc entries found",
        )
        return

    ordered_variants = [v for v in ("combined", "auth_only", "flow_only") if v in rows_by_variant]
    ordered_variants.extend(v for v in rows_by_variant if v not in ordered_variants)

    for variant in ordered_variants:
        fig, ax = plt.subplots(figsize=(10, 5))
        df = pd.DataFrame(rows_by_variant[variant], columns=["group", "auc"])
        baseline_auc = float(df.iloc[0]["auc"])
        colors = ["#4CAF50" if float(v) > baseline_auc else "#2196F3" for v in df["auc"].values]
        bars = ax.bar(df["group"], df["auc"], color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, df["auc"].values):
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01, f"{val:.2f}", ha="center", va="bottom", fontsize=7)
        ax.set_title(f"Feature Sweep — {variant.replace('_', ' ').title()}")
        ax.set_xlabel("Feature Group")
        ax.set_ylabel("Holdout Evaluation AUC")
        ax.set_ylim(0, max(1.0, float(df["auc"].max()) + 0.08))
        ax.tick_params(axis="x", rotation=35)
        for tick in ax.get_xticklabels():
            tick.set_ha("right")
        legend_handles = [
            mpatches.Patch(color="#2196F3", label="At or below base AUC"),
            mpatches.Patch(color="#4CAF50", label="Improves over base AUC"),
        ]
        ax.legend(handles=legend_handles, fontsize=7, framealpha=0.9, loc="upper left", bbox_to_anchor=(1.02, 1))
        fig.tight_layout()
        _save_fig(fig, str(output_dir / f"feature_sweep_{variant}.png"))
        plt.close(fig)
