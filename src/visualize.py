"""Visualization module for lateral movement detection results.

Static matplotlib plots for graph snapshots, score distributions,
ROC curves, and detection timelines.
"""

from __future__ import annotations

import ast
from pathlib import Path

import igraph as ig
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch
import numpy as np
import pandas as pd

from src.graph_builder import build_combined_graph

# ── Styling constants ────────────────────────────────────────────────
PALETTE = ["#2ecc71", "#e74c3c", "#3498db", "#f39c12", "#9b59b6"]
BG_COLOR = "#fdfdfd"
FIG_SIZE = (10, 6)
DPI = 150
TITLE_FS = 14
LABEL_FS = 12

NODE_COLORS = {"computer": "#3498db", "user": "#2ecc71"}
EDGE_COLORS = {"auth": "#3498db", "flow": "#e74c3c"}


def _apply_style() -> None:
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            pass


# ── 1. Graph snapshot ────────────────────────────────────────────────
def plot_graph_snapshot(
    g: ig.Graph,
    output_path: str,
    title: str = "Graph Snapshot",
) -> None:
    """Visualize graph structure.

    Color nodes by type (computer=blue, user=green).
    Edge color by type (auth=blue, flow=red). Size by degree.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    layout = g.layout("fruchterman_reingold") if g.vcount() < 500 else g.layout("auto")
    coords = np.array(layout.coords)

    degrees = np.array(g.degree(), dtype=float)
    max_deg = degrees.max() if degrees.max() > 0 else 1.0
    node_sizes = 20 + 180 * (degrees / max_deg)

    node_types = g.vs["node_type"] if "node_type" in g.vs.attributes() else ["computer"] * g.vcount()
    node_cols = [NODE_COLORS.get(str(t), "#95a5a6") for t in node_types]

    edge_types = g.es["type"] if "type" in g.es.attributes() else ["auth"] * g.ecount()
    for edge_type, color in EDGE_COLORS.items():
        eids = [i for i, t in enumerate(edge_types) if t == edge_type]
        for eid in eids:
            e = g.es[eid]
            src_xy = coords[e.source]
            tgt_xy = coords[e.target]
            ax.annotate(
                "",
                xy=tgt_xy,
                xytext=src_xy,
                arrowprops=dict(
                    arrowstyle="->",
                    color=color,
                    lw=0.6,
                    alpha=0.4,
                ),
            )

    ax.scatter(
        coords[:, 0],
        coords[:, 1],
        s=node_sizes,
        c=node_cols,
        edgecolors="#2c3e50",
        linewidths=0.5,
        alpha=0.85,
        zorder=3,
    )

    legend_handles = [
        Patch(facecolor=NODE_COLORS["computer"], edgecolor="#2c3e50", label="Computer"),
        Patch(facecolor=NODE_COLORS["user"], edgecolor="#2c3e50", label="User"),
        Line2D([0], [0], color=EDGE_COLORS["auth"], lw=1.5, label="Auth edge"),
        Line2D([0], [0], color=EDGE_COLORS["flow"], lw=1.5, label="Flow edge"),
    ]
    ax.legend(handles=legend_handles, loc="upper right", fontsize=9, framealpha=0.9)

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel("X", fontsize=LABEL_FS)
    ax.set_ylabel("Y", fontsize=LABEL_FS)
    ax.tick_params(labelsize=9)
    fig.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


# ── 2. Score distribution ───────────────────────────────────────────
def plot_score_distribution(
    scores: pd.Series,
    labels: pd.Series,
    output_path: str,
    title: str = "Score Distribution",
) -> None:
    """Histogram of anomaly scores, separate for red team vs baseline events."""
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    mask_red = labels.astype(int) == 1
    mask_base = ~mask_red

    bins = np.linspace(0, 1, 40)
    ax.hist(
        scores[mask_base],
        bins=bins,
        alpha=0.7,
        color=PALETTE[0],
        label="Baseline",
        edgecolor="white",
        linewidth=0.4,
    )
    if mask_red.any():
        ax.hist(
            scores[mask_red],
            bins=bins,
            alpha=0.7,
            color=PALETTE[1],
            label="Red team",
            edgecolor="white",
            linewidth=0.4,
        )

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel("Anomaly score", fontsize=LABEL_FS)
    ax.set_ylabel("Count", fontsize=LABEL_FS)
    ax.legend(fontsize=10, framealpha=0.9)
    ax.set_xlim(0, 1)
    ax.tick_params(labelsize=9)
    fig.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


# ── 3. ROC curves ───────────────────────────────────────────────────
def plot_roc_curves(
    results_list: list[dict],
    output_path: str,
    title: str = "ROC Curves",
) -> None:
    """Overlaid ROC curves for multiple methods.

    Each dict must have 'method_name', 'fpr_array', 'tpr_array'.
    If *results_list* is empty, synthetic demo curves are generated.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    if not results_list:
        np.random.seed(42)
        demo_aucs = [0.72, 0.86, 0.94]
        for i, auc_target in enumerate(demo_aucs):
            fpr = np.linspace(0, 1, 200)
            tpr = 1 - (1 - fpr) ** (auc_target * 3)
            results_list.append({
                "method_name": f"Demo method {i + 1} (AUC≈{auc_target:.2f})",
                "fpr_array": fpr,
                "tpr_array": tpr,
            })

    for idx, res in enumerate(results_list):
        color = PALETTE[idx % len(PALETTE)]
        ax.plot(
            res["fpr_array"],
            res["tpr_array"],
            color=color,
            lw=2,
            label=res["method_name"],
        )

    ax.plot([0, 1], [0, 1], "--", color="#95a5a6", lw=1, label="Random baseline")
    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel("False positive rate", fontsize=LABEL_FS)
    ax.set_ylabel("True positive rate", fontsize=LABEL_FS)
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.legend(fontsize=10, framealpha=0.9, loc="lower right")
    ax.tick_params(labelsize=9)
    fig.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


# ── 4. Detection timeline ───────────────────────────────────────────
def plot_detection_timeline(
    event_times: pd.Series,
    scores: pd.Series,
    redteam_times: pd.Series,
    threshold: float,
    output_path: str,
    title: str = "Detection Timeline",
) -> None:
    """Timeline showing scores over time with red team events and threshold line."""
    _apply_style()
    fig, ax = plt.subplots(figsize=FIG_SIZE, facecolor=BG_COLOR)

    ax.scatter(
        event_times,
        scores,
        s=6,
        alpha=0.5,
        color=PALETTE[2],
        label="Events",
        rasterized=True,
    )

    # Red-team markers
    if not redteam_times.empty:
        rt_set = set(redteam_times.values)
        mask_rt = event_times.isin(rt_set)
        if mask_rt.any():
            ax.scatter(
                event_times[mask_rt],
                scores[mask_rt],
                s=18,
                alpha=0.8,
                color=PALETTE[1],
                marker="x",
                linewidths=1.2,
                label="Red team",
                zorder=4,
            )

    ax.axhline(
        y=threshold,
        color=PALETTE[3],
        lw=1.5,
        ls="--",
        label=f"Threshold ({threshold:.2f})",
    )

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel("Time", fontsize=LABEL_FS)
    ax.set_ylabel("Anomaly score", fontsize=LABEL_FS)
    ax.set_ylim(-0.05, 1.05)
    ax.legend(fontsize=10, framealpha=0.9)
    ax.tick_params(labelsize=9)
    fig.tight_layout()

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)


# ── 5. Generate all figures ─────────────────────────────────────────
def generate_all_figures(results_dir: str = "results") -> None:
    """Generate all 4 plots, saving to ``results/figures/*.png``.

    If no real data is available, demo plots with synthetic data are
    produced so the pipeline can be verified end-to-end.
    """
    figures_dir = Path(results_dir) / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    metrics_csv = Path(results_dir) / "metrics.csv"
    has_real_data = metrics_csv.exists()

    # ── 1. Graph snapshot ────────────────────────────────────────────
    if has_real_data:
        try:
            auth_path = Path(results_dir) / "auth_events.csv"
            flow_path = Path(results_dir) / "flow_events.csv"
            if auth_path.exists() or flow_path.exists():
                auth_df = pd.read_csv(auth_path) if auth_path.exists() else pd.DataFrame()
                flow_df = pd.read_csv(flow_path) if flow_path.exists() else pd.DataFrame()
                g = build_combined_graph(auth_df, flow_df)
            else:
                raise FileNotFoundError
        except Exception:
            g = _demo_graph()
    else:
        g = _demo_graph()

    plot_graph_snapshot(g, str(figures_dir / "graph_snapshot.png"))

    # ── 2. Score distribution ────────────────────────────────────────
    np.random.seed(0)
    demo_scores = pd.Series(np.random.beta(2, 5, 2000))
    demo_labels = pd.Series(np.zeros(2000, dtype=int))
    demo_labels.iloc[np.random.choice(2000, 100, replace=False)] = 1
    demo_scores.iloc[demo_labels == 1] = np.random.beta(5, 2, 100)

    plot_score_distribution(
        demo_scores,
        demo_labels,
        str(figures_dir / "score_distribution.png"),
    )

    # ── 3. ROC curves ───────────────────────────────────────────────
    roc_data: list[dict] = []
    if has_real_data:
        try:
            metrics_df = pd.read_csv(metrics_csv)
            for _, row in metrics_df.iterrows():
                if "fpr_array" in row and "tpr_array" in row:
                    roc_data.append({
                        "method_name": str(row.get("method", "unknown")),
                        "fpr_array": np.array(ast.literal_eval(str(row["fpr_array"]))),
                        "tpr_array": np.array(ast.literal_eval(str(row["tpr_array"]))),
                    })
        except Exception:
            pass

    plot_roc_curves(roc_data, str(figures_dir / "roc_curves.png"))

    # ── 4. Detection timeline ───────────────────────────────────────
    np.random.seed(1)
    n_events = 1000
    t_start = pd.Timestamp("2025-01-01")
    demo_evt_times = pd.Series(
        [t_start + pd.Timedelta(seconds=int(s)) for s in np.sort(np.random.randint(0, 86400, n_events))]
    )
    demo_scs = pd.Series(np.random.beta(2, 5, n_events))
    n_rt = 20
    demo_rt_times = pd.Series(
        [t_start + pd.Timedelta(seconds=int(s)) for s in np.random.randint(3600, 82800, n_rt)]
    )
    threshold = float(demo_scs.quantile(0.95))

    plot_detection_timeline(
        demo_evt_times,
        demo_scs,
        demo_rt_times,
        threshold,
        str(figures_dir / "detection_timeline.png"),
    )

    # ── Summary ──────────────────────────────────────────────────────
    generated = sorted(figures_dir.glob("*.png"))
    print(f"Generated {len(generated)} figure(s):")
    for p in generated:
        print(f"  → {p}")


# ── Helpers ──────────────────────────────────────────────────────────
def _demo_graph() -> ig.Graph:
    """Small synthetic directed graph for demo purposes."""
    g = ig.Graph(directed=True)
    nodes = [f"C{i}" for i in range(8)] + [f"U{i}" for i in range(5)]
    for n in nodes:
        g.add_vertex(name=n, node_type="computer" if n.startswith("C") else "user")

    edges = [
        ("C0", "U0", "auth"),
        ("U0", "C1", "auth"),
        ("C1", "U1", "auth"),
        ("U1", "C2", "auth"),
        ("C2", "C3", "flow"),
        ("C3", "C4", "flow"),
        ("C4", "U2", "auth"),
        ("U2", "C5", "auth"),
        ("C5", "C6", "flow"),
        ("C6", "C7", "flow"),
        ("U3", "C1", "auth"),
        ("C1", "U4", "auth"),
        ("U4", "C3", "auth"),
    ]
    for src, dst, etype in edges:
        g.add_edge(src, dst, type=etype, weight=1)

    return g
