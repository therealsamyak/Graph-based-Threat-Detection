"""Detection-centric figure generators."""

# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportOperatorIssue=false, reportIndexIssue=false, reportMissingTypeArgument=false

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.figures.loading import (
    load_baseline_edge_scores,
    load_edge_scores,
    load_graph_data,
    load_redteam_events,
)
from src.figures.style import (
    BASE_METHOD_COLORS,
    _save_fig,
    get_method_label,
    logger,
    save_placeholder_figure,
)


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

    fig, axes = plt.subplots(1, 3, figsize=(15, 5), sharey=True)
    axes_arr = np.atleast_1d(axes)
    plotted = 0

    baseline_methods = [
        ("one_class_svm", ["one_class_svm_score", "ocsvm_score", "svm_score"]),
        ("isolation_forest", ["isolation_forest_score", "if_score", "isoforest_score"]),
    ]

    for idx, ax in enumerate(axes_arr):
        if idx >= len(variants):
            ax.axis("off")
            continue

        variant = variants[idx]
        df = load_edge_scores(results_dir, variant)
        if df is None or df.empty:
            ax.text(0.5, 0.5, f"{variant}\nno data", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(variant)
            continue

        score_col = next((c for c in ("score", "edge_score", "anomaly_score") if c in df.columns), None)
        if score_col is None:
            logger.warning("Skipping variant '%s' in score distributions: score column missing", variant)
            ax.text(0.5, 0.5, f"{variant}\nscore column missing", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(variant)
            continue

        red_col = next((c for c in ("is_redteam", "red_team", "redteam", "label") if c in df.columns), None)
        scores = pd.to_numeric(df[score_col], errors="coerce").dropna()
        if scores.empty:
            ax.text(0.5, 0.5, f"{variant}\nno score values", ha="center", va="center", transform=ax.transAxes)
            ax.set_title(variant)
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

        ax.hist(base_scores, bins=bins, alpha=0.6, color="#2ecc71", label="Normal", edgecolor="white", linewidth=0.3)
        if not red_scores.empty:
            ax.hist(red_scores, bins=bins, alpha=0.7, color="#e74c3c", label="Red team", edgecolor="white", linewidth=0.3)

        if len(base_scores) > 10:
            try:
                base_scores.plot.kde(ax=ax, color="#27ae60", linewidth=1.5, alpha=0.8)
            except Exception:
                pass
        if len(red_scores) > 10:
            try:
                red_scores.plot.kde(ax=ax, color="#c0392b", linewidth=1.5, alpha=0.8)
            except Exception:
                pass

        # Overlay baseline score KDE curves
        if baseline_df is not None and not baseline_df.empty:
            _label_col = "label" if "label" in baseline_df.columns else None
            for method, score_candidates in baseline_methods:
                bc = next((c for c in score_candidates if c in baseline_df.columns), None)
                if bc is None:
                    continue
                bvals = pd.to_numeric(baseline_df[bc], errors="coerce").dropna()
                if bvals.empty or len(bvals) < 10:
                    continue
                method_color = BASE_METHOD_COLORS.get(method, "#888888")
                method_label = get_method_label(method, variant)
                try:
                    # Plot KDE for all baseline scores (normal + redteam combined)
                    bvals.plot.kde(ax=ax, color=method_color, linewidth=2.0, alpha=0.9, linestyle="--", label=method_label)
                except Exception:
                    logger.debug("KDE failed for %s scores in variant '%s'", method, variant)

        ax.set_yscale("log")
        ax.set_title(variant)
        ax.set_xlabel("Score")
        if idx == 0:
            ax.set_ylabel("Count (log)")
        ax.legend(fontsize=7, framealpha=0.9, loc="upper right")
        plotted += 1

    if plotted == 0:
        plt.close(fig)
        logger.warning("Skipping score distributions: no plottable variant data")
        return

    fig.suptitle("Edge Score Distributions by Variant")
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "score_distributions.png"))


def plot_detection_timeline(
    results_dir: Path | None,
    baselines_dir: Path | None,
    output_dir: Path,
) -> None:
    if results_dir is None or not results_dir.exists():
        logger.warning("Skipping detection timeline: results_dir missing")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "results_dir missing",
        )
        return

    rt_df = load_redteam_events(results_dir)
    if rt_df is None or rt_df.empty:
        logger.warning("Skipping detection timeline: redteam_events unavailable")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "redteam_events unavailable",
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

    chosen_df = None
    chosen_variant = None
    for variant in variants:
        df = load_edge_scores(results_dir, variant)
        if df is None or df.empty:
            continue
        if any(c in df.columns for c in ("timestamp", "time", "ts")) and any(
            c in df.columns for c in ("score", "edge_score", "anomaly_score")
        ):
            chosen_df = df
            chosen_variant = variant
            break

    if chosen_df is None:
        logger.warning("Skipping detection timeline: no edge_scores with timestamp+score columns")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "no edge_scores with timestamp+score columns",
        )
        return

    ts_col = next(c for c in ("timestamp", "time", "ts") if c in chosen_df.columns)
    score_col = next(c for c in ("score", "edge_score", "anomaly_score") if c in chosen_df.columns)

    ts = pd.to_datetime(chosen_df[ts_col], errors="coerce")
    if ts.isna().all():
        ts = pd.to_datetime(pd.to_numeric(chosen_df[ts_col], errors="coerce"), unit="s", errors="coerce")
    scores = pd.to_numeric(chosen_df[score_col], errors="coerce")

    rt_ts_col = next((c for c in ("timestamp", "time", "ts") if c in rt_df.columns), None)
    if rt_ts_col is None:
        logger.warning("Skipping detection timeline: redteam_events has no timestamp column")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "redteam_events has no timestamp column",
        )
        return
    rt_ts = pd.to_datetime(rt_df[rt_ts_col], errors="coerce")
    if rt_ts.isna().all():
        rt_ts = pd.to_datetime(pd.to_numeric(rt_df[rt_ts_col], errors="coerce"), unit="s", errors="coerce")
    rt_set = set(rt_ts.dropna())

    red_col = next((c for c in ("is_redteam", "red_team", "redteam", "label") if c in chosen_df.columns), None)
    if red_col is not None:
        mask_rt = pd.to_numeric(chosen_df[red_col], errors="coerce").fillna(0).astype(int) == 1
    else:
        mask_rt = ts.isin(rt_set)

    valid = (~ts.isna()) & (~scores.isna())
    if valid.sum() == 0:
        logger.warning("Skipping detection timeline: no valid timestamp/score rows")
        save_placeholder_figure(
            str(output_dir / "detection_timeline.png"),
            "Detection Timeline",
            "no valid timestamp/score rows",
        )
        return

    fig, ax = plt.subplots(figsize=(12, 5))
    ax.scatter(ts[valid & ~mask_rt], scores[valid & ~mask_rt], s=6, alpha=0.35, color="#3498db", label="Normal", rasterized=True)
    ax.scatter(ts[valid & mask_rt], scores[valid & mask_rt], s=24, alpha=0.9, color="#e74c3c", marker="x", linewidths=1.2, label="Red team")

    threshold = None
    for th_col in ("threshold", "detection_threshold"):
        if th_col in chosen_df.columns:
            th_vals = pd.to_numeric(chosen_df[th_col], errors="coerce").dropna()
            if not th_vals.empty:
                threshold = float(th_vals.iloc[0])
                break
    if threshold is not None:
        ax.axhline(y=threshold, color="#f39c12", lw=1.5, ls="--", label=f"Threshold ({threshold:.2f})")

    # Check if baseline methods have timestamp data for multi-method timeline
    has_baseline_ts = False
    if baselines_dir is not None and baselines_dir.exists() and chosen_variant is not None:
        baseline_df = load_baseline_edge_scores(baselines_dir, chosen_variant)
        if baseline_df is not None and any(c in baseline_df.columns for c in ("timestamp", "time", "ts")):
            has_baseline_ts = True

    title = "Detection Timeline — Red Team vs Normal Activity"
    if baselines_dir is not None and baselines_dir.exists() and not has_baseline_ts:
        title += "\n(Baseline methods: no timestamp data available)"

    ax.set_title(title)
    ax.set_xlabel("Timestamp")
    ax.set_ylabel("Score")
    ax.legend(framealpha=0.9, fontsize=9, loc="upper right")
    fig.autofmt_xdate()
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "detection_timeline.png"))
    logger.info("Detection timeline plotted using variant '%s'", chosen_variant)


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
        elif edges_df is not None and not edges_df.empty and {"source", "target"}.issubset(edges_df.columns):
            node_count = int(pd.unique(pd.concat([edges_df["source"], edges_df["target"]], axis=0)).shape[0])
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

    fig, ax = plt.subplots(figsize=(12, 6))
    palette = ["#2196F3", "#4CAF50", "#FF9800", "#9C27B0"]
    for i, (metric, label) in enumerate(zip(metrics, labels)):
        offset = (i - 1.5) * width
        ax.bar(x + offset, df[metric].values, width, label=label, color=palette[i], alpha=0.85, edgecolor="white", linewidth=0.5)

    ax.set_xticks(x)
    ax.set_xticklabels(df["variant"].tolist())
    ax.set_title("Graph Topology Statistics by Variant")
    ax.set_xlabel("Variant")
    ax.set_ylabel("Value")
    ax.legend(framealpha=0.9)
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "graph_statistics.png"))


def plot_holdout_validation(analysis_data: dict | None, output_dir: Path) -> None:
    if analysis_data is None:
        logger.warning("Skipping holdout validation: analysis_data is None")
        save_placeholder_figure(
            str(output_dir / "holdout_validation.png"),
            "Holdout Validation",
            "analysis_data is None",
        )
        return

    holdout = analysis_data.get("holdout_results", {})
    if not isinstance(holdout, dict) or not holdout:
        holdout = analysis_data.get("optimization_holdout", {})
    if not isinstance(holdout, dict) or not holdout:
        logger.warning("Skipping holdout validation: holdout_results not found")
        save_placeholder_figure(
            str(output_dir / "holdout_validation.png"),
            "Holdout Validation",
            "holdout_results not found",
        )
        return

    def _first_value(container: dict, keys: tuple[str, ...]) -> float | None:
        for key in keys:
            val = container.get(key)
            if val is not None:
                try:
                    return float(val)
                except (TypeError, ValueError):
                    continue
        return None

    opt = _first_value(holdout, ("eval_auc", "auc", "optimized_auc", "best_auc"))
    lr = _first_value(holdout, ("lr_baseline", "baseline_auc", "logreg_auc", "lr_auc"))
    cal = _first_value(holdout, ("calibrated", "calibrated_auc", "calibration_auc"))

    if opt is None and isinstance(holdout.get("optimized"), dict):
        opt = _first_value(holdout["optimized"], ("eval_auc", "auc"))
    if lr is None and isinstance(holdout.get("baseline"), dict):
        lr = _first_value(holdout["baseline"], ("eval_auc", "auc", "lr_auc"))
    if cal is None and isinstance(holdout.get("calibration"), dict):
        cal = _first_value(holdout["calibration"], ("eval_auc", "auc", "calibrated_auc"))

    vals = [opt, lr, cal]
    if all(v is None for v in vals):
        logger.warning("Skipping holdout validation: no AUC values found")
        save_placeholder_figure(
            str(output_dir / "holdout_validation.png"),
            "Holdout Validation",
            "no AUC values found",
        )
        return

    plot_vals = [0.0 if v is None else float(v) for v in vals]
    labels = ["Optimized", "LR Baseline", "Calibrated"]
    colors = ["#2196F3", "#FF9800", "#4CAF50"]

    fig, ax = plt.subplots()
    bars = ax.bar(labels, plot_vals, color=colors, alpha=0.85, edgecolor="white", linewidth=0.5)
    for bar, val in zip(bars, vals):
        text = "n/a" if val is None else f"{val:.3f}"
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01, text, ha="center", va="bottom", fontsize=9)

    ax.set_ylim(0, max(1.0, max(plot_vals) + 0.08))
    ax.set_ylabel("AUC")
    ax.set_title("Holdout Validation — Optimized vs Baseline")
    fig.tight_layout()
    _save_fig(fig, str(output_dir / "holdout_validation.png"))
