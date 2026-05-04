"""Graph snapshot plotting."""

from __future__ import annotations

import igraph as ig
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Patch

from src.visualization.style import (
    _apply_style,
    _save_fig,
    BG_COLOR,
    FIG_SIZE,
    TITLE_FS,
    NODE_COLORS,
    EDGE_COLORS,
)


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

    if total_nodes > 500:
        degrees = np.array(g.degree(), dtype=float)
        top_k = min(200, total_nodes)
        top_indices = np.argsort(degrees)[-top_k:].tolist()

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

    if vcount <= 2000:
        layout = g.layout("fruchterman_reingold")
    else:
        layout = g.layout("auto")
    coords = np.array(layout.coords)

    degrees = np.array(g.degree(), dtype=float)
    max_deg = degrees.max() if degrees.max() > 0 else 1.0
    node_sizes = 10 + 100 * (degrees / max_deg)
    node_sizes = np.clip(node_sizes, 5, None)

    node_attrs = g.vs.attributes()
    if "node_type" in node_attrs:
        node_types = g.vs["node_type"]
    else:
        node_types = ["computer"] * vcount
    node_cols = [NODE_COLORS.get(str(t), "#95a5a6") for t in node_types]

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

    ax.scatter(
        coords[:, 0], coords[:, 1],
        s=node_sizes, c=node_cols, edgecolors="#2c3e50",
        linewidths=0.5, alpha=0.85, zorder=3,
    )

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

    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_frame_on(False)
    fig.tight_layout()
    _save_fig(fig, output_path)
