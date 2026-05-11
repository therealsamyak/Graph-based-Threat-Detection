"""Shared utilities replacing duplicated code across the codebase."""

from __future__ import annotations

import igraph as ig
import pandas as pd


def compute_edge_pair_names(g: ig.Graph) -> list[tuple[str, str]]:
    """Extract (source_name, target_name) pairs for all edges in the graph."""
    return [
        (g.vs[e.source]["name"], g.vs[e.target]["name"])
        for e in g.es
    ]


FLOW_AGG_COLUMNS: list[str] = [
    "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
    "Total Length of Fwd Packet", "Total Length of Bwd Packet",
    "Flow Bytes/s", "Flow Packets/s",
    "Fwd Packet Length Mean", "Bwd Packet Length Mean",
    "Fwd Packets/s", "Bwd Packets/s",
    "Flow IAT Mean", "Packet Length Mean",
]


def build_dapt_graph(
    df: pd.DataFrame,
    flow_agg_columns: list[str] | None = None,
) -> tuple[ig.Graph, pd.DataFrame]:
    agg_cols = flow_agg_columns or FLOW_AGG_COLUMNS
    agg_cols_available = [c for c in agg_cols if c in df.columns]
    group_cols = ["Src IP", "Dst IP"]

    agg_dict: dict = {"is_lateral_movement": "max"}
    for c in agg_cols_available:
        agg_dict[c] = "mean"
    if "Protocol" in df.columns:
        agg_dict["Protocol"] = "first"

    grouped = df.groupby(group_cols, as_index=False).agg(agg_dict)

    g = ig.Graph(directed=True)
    node_set: set[str] = set()

    for _, row in grouped.iterrows():
        src = str(row["Src IP"])
        dst = str(row["Dst IP"])
        if src not in node_set:
            g.add_vertex(src, node_type="computer", is_machine=True)
            node_set.add(src)
        if dst not in node_set:
            g.add_vertex(dst, node_type="computer", is_machine=True)
            node_set.add(dst)

        edge_attrs: dict = {"type": "flow", "weight": 1}
        for c in agg_cols_available:
            val = row.get(c)
            if val is not None:
                try:
                    edge_attrs[c] = float(val)
                except (ValueError, TypeError):
                    pass
        if "Protocol" in row.index:
            edge_attrs["protocol"] = str(row["Protocol"])
        g.add_edge(src, dst, **edge_attrs)

    return g, grouped
