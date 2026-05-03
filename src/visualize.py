"""Publication-quality visualization module for lateral movement detection.

Generates ROC curves, score distributions, detection timelines,
graph snapshots, and method comparison bar charts.
"""

from __future__ import annotations

from pathlib import Path

import igraph as ig
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

try:
    from matplotlib.dates import DateFormatter as _DateFormatter
    _HAS_DATEFORMATTER = True
except ImportError:
    _DateFormatter = None
    _HAS_DATEFORMATTER = False

try:
    from scipy.stats import gaussian_kde as _gaussian_kde
    _HAS_SCIPY_KDE = True
except ImportError:
    _gaussian_kde = None
    _HAS_SCIPY_KDE = False

# ── Styling constants ────────────────────────────────────────────────
PALETTE = ["#2ecc71", "#e74c3c", "#3498db", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22"]
LINE_STYLES = ["-", "--", "-.", ":", "-", "--", "-."]
BG_COLOR = "#fdfdfd"
FIG_SIZE = (10, 6)
DPI = 150
TITLE_FS = 14
LABEL_FS = 12

NODE_COLORS = {"computer": "#3498db", "user": "#2ecc71"}
EDGE_COLORS = {"auth": "#3498db", "flow": "#e74c3c"}


def _apply_style() -> None:
    """Apply a clean matplotlib style with fallback."""
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            pass


def _save_fig(fig, output_path: str) -> None:
    """Save figure and close."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


# ── 1. ROC Curves ───────────────────────────────────────────────────
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

        # Use empirical arrays if provided and non-trivial
        if (fpr_arr is not None and tpr_arr is not None
                and hasattr(fpr_arr, "__len__") and len(fpr_arr) > 3):
            fpr = np.asarray(fpr_arr, dtype=float)
            tpr = np.asarray(tpr_arr, dtype=float)
        else:
            # Synthesize a smooth ROC curve from the AUC value
            fpr = np.linspace(0, 1, 300)
            ratio = auc_val / (1 - auc_val + 1e-9)
            tpr = 1 - (1 - fpr) ** ratio

        label = f"{name} (AUC = {auc_val:.3f})" if auc_val > 0 else name
        ax.plot(fpr, tpr, color=color, lw=2, ls=ls, label=label)

    # Random baseline
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


# ── 2. Score Distribution ───────────────────────────────────────────
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

    # KDE overlay
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


# ── 3. Detection Timeline ───────────────────────────────────────────
def plot_detection_timeline(
    event_times: pd.Series,
    scores: pd.Series,
    threshold: float,
    output_path: str,
    redteam_edge_indices: set[int] | None = None,
    title: str = "Detection Timeline",
) -> None:
    """Scatter timeline of anomaly scores over time with red team markers.

    Handles Unix timestamps, datetime, or sequential indices.
    Subsamples non-red-team points when > 10000 for performance.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(12, 5), facecolor=BG_COLOR)

    times = event_times.copy()
    use_datetime = False

    # Detect timestamp type
    if times.dtype in (np.float64, np.int64, np.float32, np.int32):
        numeric_times = pd.to_numeric(times, errors="coerce").dropna()
        if len(numeric_times) > 0 and numeric_times.max() > 1e9:
            times_dt = pd.to_datetime(numeric_times, unit="s")
            times = pd.Series(times_dt, index=numeric_times.index)
            use_datetime = True
        elif numeric_times.nunique() <= 1:
            # All zeros or constant — fall back to sequential index
            times = pd.Series(range(len(scores)), index=scores.index)
    elif pd.api.types.is_datetime64_any_dtype(times):
        use_datetime = True

    # Build masks
    if redteam_edge_indices is not None:
        mask_rt = pd.Series(False, index=scores.index)
        valid_idx = [i for i in redteam_edge_indices if i in scores.index]
        if valid_idx:
            mask_rt.loc[valid_idx] = True
    else:
        mask_rt = pd.Series(False, index=scores.index)

    # Subsample for performance
    n_total = len(scores)
    n_rt = mask_rt.sum()
    if n_total > 10000 and (n_total - n_rt) > 5000:
        non_rt_idx = scores.index[~mask_rt]
        sampled = np.random.choice(non_rt_idx, size=5000, replace=False)
        plot_idx = list(sampled) + list(scores.index[mask_rt])
        plot_idx = sorted(set(plot_idx))
    else:
        plot_idx = scores.index.tolist()

    # All events (blue/gray dots)
    ax.scatter(
        times.loc[plot_idx], scores.loc[plot_idx],
        s=4, alpha=0.3, color="#3498db", label="Events", rasterized=True, zorder=2,
    )

    # Red team markers
    if mask_rt.any():
        rt_loc = scores.index[mask_rt]
        ax.scatter(
            times.loc[rt_loc], scores.loc[rt_loc],
            s=20, alpha=0.8, color="#e74c3c", marker="x", linewidths=1.2,
            label="Red team", zorder=4,
        )

    # Threshold line
    ax.axhline(
        y=threshold, color="#f39c12", lw=1.5, ls="--",
        label=f"Threshold ({threshold:.2f})",
    )

    # Y-axis auto-range
    y_lo = min(0, scores.min() - 0.05)
    y_hi = scores.max() * 1.1
    ax.set_ylim(y_lo, y_hi)

    # X-axis formatting
    if use_datetime and _HAS_DATEFORMATTER:
        ax.xaxis.set_major_formatter(_DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        x_label = "Time"
    elif "index" not in str(times.iloc[0]) if len(times) > 0 else True:
        x_label = "Event Index"
    else:
        x_label = "Time"

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel(x_label, fontsize=LABEL_FS)
    ax.set_ylabel("Anomaly Score", fontsize=LABEL_FS)
    ax.legend(fontsize=9, framealpha=0.9, loc="upper right")
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    _save_fig(fig, output_path)


# ── 4. Graph Snapshot ────────────────────────────────────────────────
def plot_graph_snapshot(
    g: ig.Graph,
    output_path: str,
    title: str = "Graph Snapshot",
) -> None:
    """Visualize graph structure with node coloring by type.

    For large graphs (>500 nodes), extracts a subgraph of the
    highest-degree nodes and their neighbors for readability.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    if g.vcount() == 0:
        ax.text(0.5, 0.5, "Empty graph", ha="center", va="center",
                transform=ax.transAxes, fontsize=13, color="#95a5a6")
        _save_fig(fig, output_path)
        return

    total_nodes = g.vcount()
    total_edges = g.ecount()
    subtitle = ""

    # Subgraph extraction for large graphs
    if total_nodes > 500:
        degrees = np.array(g.degree(), dtype=float)
        top_k = min(200, total_nodes)
        top_indices = np.argsort(degrees)[-top_k:].tolist()

        # Add neighbors up to 500 total
        neighbor_set = set(top_indices)
        for n in top_indices:
            neighbors = g.neighbors(n)
            for nb in neighbors:
                neighbor_set.add(nb)
                if len(neighbor_set) >= 500:
                    break
            if len(neighbor_set) >= 500:
                break

        sub_nodes = sorted(neighbor_set)
        g = g.subgraph(sub_nodes)
        subtitle = f"Subgraph: {g.vcount():,} of {total_nodes:,} nodes shown"

    vcount = g.vcount()

    # Layout
    if vcount <= 2000:
        layout = g.layout("fruchterman_reingold")
    else:
        layout = g.layout("auto")
    coords = np.array(layout.coords)

    # Node sizing by degree
    degrees = np.array(g.degree(), dtype=float)
    max_deg = degrees.max() if degrees.max() > 0 else 1.0
    node_sizes = 10 + 100 * (degrees / max_deg)
    node_sizes = np.clip(node_sizes, 5, None)

    # Node coloring by type
    node_attrs = g.vs.attributes()
    if "node_type" in node_attrs:
        node_types = g.vs["node_type"]
    else:
        node_types = ["computer"] * vcount
    node_cols = [NODE_COLORS.get(str(t), "#95a5a6") for t in node_types]

    # Draw edges with ax.plot for performance
    edge_attrs = g.es.attributes()
    if "type" in edge_attrs:
        edge_types = g.es["type"]
    else:
        edge_types = ["auth"] * g.ecount()

    for edge_type, color in EDGE_COLORS.items():
        eids = [i for i, t in enumerate(edge_types) if str(t) == edge_type]
        if not eids:
            continue
        segments_x = []
        segments_y = []
        for eid in eids:
            e = g.es[eid]
            segments_x.extend([coords[e.source, 0], coords[e.target, 0], np.nan])
            segments_y.extend([coords[e.source, 1], coords[e.target, 1], np.nan])
        ax.plot(segments_x, segments_y, color=color, lw=0.4, alpha=0.3, zorder=1)

    # Draw nodes
    ax.scatter(
        coords[:, 0], coords[:, 1],
        s=node_sizes, c=node_cols, edgecolors="#2c3e50",
        linewidths=0.5, alpha=0.85, zorder=3,
    )

    # Legend
    legend_handles = [
        Patch(facecolor=NODE_COLORS["computer"], edgecolor="#2c3e50", label="Computer"),
        Patch(facecolor=NODE_COLORS["user"], edgecolor="#2c3e50", label="User"),
        Line2D([0], [0], color=EDGE_COLORS["auth"], lw=1.5, alpha=0.6, label="Auth edge"),
        Line2D([0], [0], color=EDGE_COLORS["flow"], lw=1.5, alpha=0.6, label="Flow edge"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=9, framealpha=0.9)

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    if subtitle:
        ax.set_title(subtitle, fontsize=9, color="#7f8c8d", pad=22)
    else:
        ax.set_title(f"{total_nodes:,} nodes, {total_edges:,} edges",
                      fontsize=9, color="#7f8c8d", pad=22)

    # Clean graph look — no axis ticks
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    fig.tight_layout()
    _save_fig(fig, output_path)


# ── 5. Method Comparison ────────────────────────────────────────────
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

    # Determine datasets
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

            # Annotate values
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
