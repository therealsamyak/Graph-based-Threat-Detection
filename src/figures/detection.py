"""Detection-centric figure generators."""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOperatorIssue=false, reportIndexIssue=false, reportMissingTypeArgument=false

from __future__ import annotations

from pathlib import Path
from typing import cast

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.loading import (
    load_baseline_edge_scores,
    load_edge_scores,
    load_graph_data,
)
from src.figures.style import (
    BASE_METHOD_COLORS,
    _save_fig,
    get_method_label,
    logger,
    save_placeholder_figure,
)
from src.visualization.style import _smart_legend_loc


def plot_score_distributions(
    results_dir: Path | None,
    baselines_dir: Path | None,
    output_dir: Path,
) -> None:
    if results_dir is None or not results_dir.exists():
        logger.warning("Skipping score distributions: results_dir missing")
        return

    variant_parent = results_dir / "LANL-2015"
    scan_root = variant_parent if variant_parent.is_dir() else results_dir
    variant_dirs = sorted([d for d in scan_root.iterdir() if d.is_dir() and d.name != "redteam"])
    if not variant_dirs:
        logger.warning("Skipping score distributions: no variant directories in %s", scan_root)
        return

    variants = [d.name for d in variant_dirs][:3]
    if not variants:
        logger.warning("Skipping score distributions: no variants discovered")
        return

    # Pre-load baseline edge scores per variant (graceful: None if unavailable)
    baseline_scores_map: dict[str, pd.DataFrame | None] = {}
    if baselines_dir is not None and baselines_dir.exists():
        for variant in variants:
            baseline_scores_map[variant] = load_baseline_edge_scores(baselines_dir, variant)

    baseline_methods = [
        ("one_class_svm", ["one_class_svm_score", "ocsvm_score", "svm_score"]),
        ("isolation_forest", ["isolation_forest_score", "if_score", "isoforest_score"]),
    ]

    plotted = 0
    for variant in variants:
        df = load_edge_scores(results_dir, variant)
        if df is None or df.empty:
            continue

        score_col = next((c for c in ("score", "edge_score", "anomaly_score") if c in df.columns), None)
        if score_col is None:
            logger.warning("Skipping variant '%s' in score distributions: score column missing", variant)
            continue

        red_col = next((c for c in ("is_redteam", "red_team", "redteam", "label") if c in df.columns), None)
        scores = pd.to_numeric(df[score_col], errors="coerce").dropna()
        if scores.empty:
            continue

        if red_col is not None:
            red_mask = pd.to_numeric(df[red_col], errors="coerce").fillna(0).astype(int) == 1
        else:
            red_mask = pd.Series(False, index=df.index)
            logger.warning("Variant '%s' has no red-team label column; plotting as normal only", variant)

        base_scores = pd.to_numeric(df.loc[~red_mask, score_col], errors="coerce").dropna()
        red_scores = pd.to_numeric(df.loc[red_mask, score_col], errors="coerce").dropna()

        lo = float(scores.min())
        hi = float(scores.max())

        # Compute global range including baseline scores for consistent bins
        baseline_df = baseline_scores_map.get(variant)
        if baseline_df is not None and not baseline_df.empty:
            for _method, score_candidates in baseline_methods:
                bc = next((c for c in score_candidates if c in baseline_df.columns), None)
                if bc is not None:
                    bvals = pd.to_numeric(baseline_df[bc], errors="coerce").dropna()
                    if not bvals.empty:
                        lo = min(lo, float(bvals.min()))
                        hi = max(hi, float(bvals.max()))

        bins = np.linspace(lo, hi, 50) if hi > lo else np.linspace(lo - 1e-6, hi + 1e-6, 50)

        fig, ax = plt.subplots(figsize=(12, 7))
        ax.hist(base_scores, bins=bins, alpha=0.6, color="#2ecc71", label="Normal", edgecolor="white", linewidth=0.3)
        if not red_scores.empty:
            ax.hist(red_scores, bins=bins, alpha=0.7, color="#e74c3c", label="Red team", edgecolor="white", linewidth=0.3)

        # Overlay baseline scores as count histograms too. KDE densities on a log-count
        # axis make the figure look synthetic because density values can be tiny.
        if baseline_df is not None and not baseline_df.empty:
            for method, score_candidates in baseline_methods:
                bc = next((c for c in score_candidates if c in baseline_df.columns), None)
                if bc is None:
                    continue
                bvals = pd.to_numeric(baseline_df[bc], errors="coerce").dropna()
                if bvals.empty:
                    continue
                method_color = BASE_METHOD_COLORS.get(method, "#888888")
                method_label = get_method_label(method, variant)
                ax.hist(
                    bvals,
                    bins=bins,
                    histtype="step",
                    color=method_color,
                    linewidth=1.8,
                    linestyle="--",
                    label=method_label,
                )

        ax.set_yscale("log")
        ax.set_title(f"Anomaly scores cluster tightly for {variant}, separating benign from malicious traffic", fontweight="bold", fontsize=21)
        ax.set_xlabel("Anomaly Score")
        ax.set_ylabel("Count (log scale)")
        ax.legend(fontsize=14, **_smart_legend_loc(ax))
        fig.tight_layout()
        _save_fig(fig, str(output_dir / f"score_distributions_{variant}.png"))
        plt.close(fig)
        plotted += 1

    if plotted == 0:
        logger.warning("Skipping score distributions: no plottable variant data")
        return


def _numeric_time(series: pd.Series) -> pd.Series:
    numeric = cast(pd.Series, pd.to_numeric(series, errors="coerce"))
    if bool(numeric.notna().any()):
        return numeric
    dt = cast(pd.Series, pd.to_datetime(series, errors="coerce"))
    seconds = pd.Series(dt.astype("int64") / 1_000_000_000, index=series.index)
    return cast(pd.Series, seconds.where(dt.notna()))


def plot_detection_timeline(
    results_dir: Path | None,
    baselines_dir: Path | None,
    output_dir: Path,
) -> None:
    _ = baselines_dir
    if results_dir is None or not results_dir.exists():
        logger.warning("Skipping detection timeline: results_dir missing")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "results_dir missing",
        )
        return

    variant_parent = results_dir / "LANL-2015"
    scan_root = variant_parent if variant_parent.is_dir() else results_dir
    variants = [d.name for d in sorted(scan_root.iterdir()) if d.is_dir() and d.name != "redteam"]
    if not variants:
        logger.warning("Skipping detection timeline: no variants discovered")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "no variants discovered",
        )
        return

    panel_data: list[tuple[str, pd.Series, pd.Series, pd.Series]] = []
    for variant in variants:
        df = load_edge_scores(results_dir, variant)
        if df is None or df.empty:
            continue
        ts_col = next((c for c in ("timestamp", "time", "ts") if c in df.columns), None)
        score_col = next((c for c in ("score", "edge_score", "anomaly_score") if c in df.columns), None)
        if ts_col is None or score_col is None:
            logger.info("Detection timeline omits variant '%s': timestamp or score column missing", variant)
            continue

        ts = _numeric_time(df[ts_col])
        scores = pd.to_numeric(df[score_col], errors="coerce")
        red_col = next((c for c in ("is_redteam", "red_team", "redteam", "label") if c in df.columns), None)
        if red_col is None:
            mask_rt = pd.Series(False, index=df.index)
        else:
            mask_rt = pd.to_numeric(df[red_col], errors="coerce").fillna(0).astype(int) == 1
        valid = (~ts.isna()) & (~scores.isna())
        if valid.any():
            panel_data.append((variant, ts[valid], scores[valid], mask_rt[valid]))

    if not panel_data:
        logger.warning("Skipping detection timeline: no valid timestamp/score rows")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "no valid timestamp/score rows",
        )
        return

    for variant, ts, scores, mask_rt in panel_data:
        fig, ax = plt.subplots(figsize=(14, 7))
        ax.scatter(ts[~mask_rt], scores[~mask_rt], s=5, alpha=0.25, color="#3498db", label="Normal", rasterized=True)
        if mask_rt.any():
            ax.scatter(ts[mask_rt], scores[mask_rt], s=24, alpha=0.9, color="#e74c3c", marker="x", linewidths=1.2, label="Red team")
        ax.set_title(f"Detection events cluster around active attack phases in {variant.replace('_', ' ').title()}", fontweight="bold", fontsize=21)
        ax.set_xlabel("Time (seconds)")
        ax.set_ylabel("Anomaly Score")
        ax.legend(fontsize=14, **_smart_legend_loc(ax))
        fig.tight_layout()
        _save_fig(fig, str(output_dir / f"detection_timeline_{variant}.png"))
        plt.close(fig)
    logger.info("Detection timeline plotted for %d variants", len(panel_data))


def plot_graph_statistics(results_dir: Path | None, output_dir: Path) -> None:
    if results_dir is None or not results_dir.exists():
        logger.warning("Skipping graph statistics: results_dir missing")
        return

    variant_parent = results_dir / "LANL-2015"
    scan_root = variant_parent if variant_parent.is_dir() else results_dir
    variants = [d.name for d in sorted(scan_root.iterdir()) if d.is_dir() and d.name != "redteam"]
    if not variants:
        logger.warning("Skipping graph statistics: no variants discovered")
        return

    rows = []
    for variant in variants:
        graph_data = load_graph_data(results_dir, variant)
        if graph_data is None:
            continue
        edges_df, nodes_df = graph_data
        edge_count = int(len(edges_df)) if edges_df is not None else 0
        if nodes_df is not None and not nodes_df.empty:
            node_count = int(len(nodes_df))
        elif edges_df is not None and not edges_df.empty:
            if {"src", "dst"}.issubset(edges_df.columns):
                node_count = int(pd.unique(pd.concat([edges_df["src"], edges_df["dst"]], axis=0)).shape[0])
            elif {"source", "target"}.issubset(edges_df.columns):
                node_count = int(pd.unique(pd.concat([edges_df["source"], edges_df["target"]], axis=0)).shape[0])
            else:
                node_count = 0
        else:
            node_count = 0

        density = float(edge_count / (node_count * (node_count - 1))) if node_count > 1 else 0.0
        avg_degree = float((2 * edge_count) / node_count) if node_count > 0 else 0.0
        rows.append((variant, node_count, edge_count, density, avg_degree))

    if not rows:
        logger.warning("Skipping graph statistics: no graph data loaded")
        return

    df = pd.DataFrame(rows, columns=["variant", "nodes", "edges", "density", "avg_degree"])
    metrics = ["nodes", "edges", "density", "avg_degree"]
    labels = ["Nodes", "Edges", "Density", "Avg Degree"]
    x = np.arange(len(df))
    width = 0.2

    fig, ax = plt.subplots(figsize=(14, 8))
    palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0"]
    for i, (metric, label) in enumerate(zip(metrics, labels)):
        offset = (i - 1.5) * width
        ax.bar(x + offset, df[metric].values, width, label=label, color=palette[i], alpha=0.85, edgecolor="white", linewidth=0.5)

    ax.set_yscale("log")
    ax.set_xticks(x)
    ax.set_xticklabels([v.replace("_", " ").title() for v in df["variant"].tolist()])
    ax.set_title("Graph topology differs significantly across attack variants", fontweight="bold", fontsize=21)
    ax.set_xlabel("Data Variant")
    ax.set_ylabel("Value (log scale)")
    ax.legend(**_smart_legend_loc(ax))
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "graph_statistics.png"))


def _holdout_data_by_variant(analysis_data: dict | None) -> dict[str, dict]:
    if not isinstance(analysis_data, dict):
        return {}
    per_variant = analysis_data.get("per_variant")
    if isinstance(per_variant, dict):
        out: dict[str, dict] = {}
        for variant, variant_data in per_variant.items():
            if not isinstance(variant_data, dict):
                continue
            holdout = variant_data.get("holdout_results") or variant_data.get("optimization_holdout")
            if isinstance(holdout, dict):
                out[str(variant)] = holdout
        if out:
            return out
    holdout = analysis_data.get("holdout_results") or analysis_data.get("optimization_holdout")
    if isinstance(holdout, dict):
        return {"combined": holdout}
    return {}


def _first_float(container: dict, keys: tuple[str, ...]) -> float | None:
    for key in keys:
        val = container.get(key)
        if val is not None:
            try:
                return float(val)
            except (TypeError, ValueError):
                continue
    return None


def _nested_float(container: dict, container_keys: tuple[str, ...], value_keys: tuple[str, ...]) -> float | None:
    for key in container_keys:
        nested = container.get(key)
        if isinstance(nested, dict):
            value = _first_float(nested, value_keys)
            if value is not None:
                return value
    return None


def plot_holdout_validation(analysis_data: dict | None, output_dir: Path) -> None:
    holdouts = _holdout_data_by_variant(analysis_data)
    if not holdouts:
        logger.warning("Skipping holdout validation: holdout_results not found")
        save_placeholder_figure(
            str(output_dir / "holdout_validation.png"),
            "Holdout Validation",
            "holdout_results not found",
        )
        return

    rows: dict[str, tuple[float | None, float | None]] = {}
    for variant, holdout in holdouts.items():
        opt_eval = _first_float(holdout, ("eval_auc", "auc", "optimized_auc", "best_auc"))
        if opt_eval is None:
            opt_eval = _nested_float(holdout, ("optimizer", "optimized"), ("auc_eval", "eval_auc", "auc"))
        lr_eval = _first_float(holdout, ("lr_baseline", "baseline_auc", "logreg_auc", "lr_auc"))
        if lr_eval is None:
            lr_eval = _nested_float(holdout, ("logistic_regression", "baseline", "lr"), ("auc_eval", "eval_auc", "auc", "lr_auc"))
        if any(v is not None for v in (opt_eval, lr_eval)):
            rows[variant] = (opt_eval, lr_eval)

    if not rows:
        logger.warning("Skipping holdout validation: no AUC values found")
        save_placeholder_figure(
            str(output_dir / "holdout_validation.png"),
            "Holdout Validation",
            "no AUC values found",
        )
        return

    ordered_variants = [v for v in ("combined", "auth_only", "flow_only") if v in rows]
    ordered_variants.extend(v for v in rows if v not in ordered_variants)
    labels = ["Optimized Model", "Logistic Regression"]
    colors = ["#2196F3", "#FF9800"]
    x = np.arange(len(ordered_variants))
    width = 0.32

    fig, ax = plt.subplots(figsize=(12, 7))
    for idx, label in enumerate(labels):
        vals = [rows[variant][idx] for variant in ordered_variants]
        plot_vals = [0.0 if val is None else val for val in vals]
        bars = ax.bar(x + (idx - 0.5) * width, plot_vals, width, label=label, color=colors[idx], alpha=0.85, edgecolor="white", linewidth=0.5)
        for bar, val in zip(bars, vals):
            text = "n/a" if val is None else f"{val:.3f}"
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01, text, ha="center", va="bottom", fontsize=14)

    ax.set_xticks(x)
    ax.set_xticklabels([v.replace("_", " ").title() for v in ordered_variants])
    ax.set_ylim(0, 1.08)
    ax.set_ylabel("Holdout AUC")
    ax.set_xlabel("Feature Set")
    ax.set_title("Optimized model outperforms logistic regression on held-out data", fontweight="bold", fontsize=21)
    ax.legend(**_smart_legend_loc(ax))
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "holdout_validation.png"))
