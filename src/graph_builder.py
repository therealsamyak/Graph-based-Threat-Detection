"""Build directed igraph graphs from LANL-2015 auth+flow events."""

from __future__ import annotations

import igraph as ig
import pandas as pd


def _clean_str(val) -> str:
    try:
        if pd.isna(val):
            return "unknown"
    except (TypeError, ValueError):
        pass
    return str(val)


def _clean_num(val):
    try:
        if pd.isna(val):
            return 0
    except (TypeError, ValueError):
        pass
    return val


def _collect_nodes(auth_df: pd.DataFrame, flow_df: pd.DataFrame) -> tuple[set[str], set[str]]:
    computers: set[str] = set()
    users: set[str] = set()

    if not auth_df.empty:
        for _, row in auth_df.iterrows():
            computers.update([_clean_str(row.get("src_comp")), _clean_str(row.get("dst_comp"))])
            users.update([_clean_str(row.get("src_user")), _clean_str(row.get("dst_user"))])

    if not flow_df.empty:
        for _, row in flow_df.iterrows():
            computers.update([_clean_str(row.get("src_comp")), _clean_str(row.get("dst_comp"))])

    return computers, users


def _is_machine_account(name: str) -> bool:
    """Check if name is a machine account (contains '$' before '@')."""
    return "$" in name.split("@")[0] if "@" in name else name.endswith("$")


def _add_nodes(g: ig.Graph, computers: set[str], users: set[str]) -> None:
    existing: set[str] = set(g.vs["name"]) if g.vcount() > 0 else set()
    for name in computers - existing:
        g.add_vertex(name, node_type="computer", is_machine=_is_machine_account(name))
    for name in users - existing:
        g.add_vertex(name, node_type="user", is_machine=_is_machine_account(name))


def _build_auth_edges(auth_df: pd.DataFrame) -> list[tuple[str, str, dict]]:
    if auth_df.empty:
        return []

    edge_map: dict[tuple[str, str], tuple[dict, int]] = {}

    for _, row in auth_df.iterrows():
        src_c, dst_c = _clean_str(row.get("src_comp")), _clean_str(row.get("dst_comp"))
        src_u, dst_u = _clean_str(row.get("src_user")), _clean_str(row.get("dst_user"))

        base = {
            "type": "auth",
            "auth_type": _clean_str(row.get("auth_type")),
            "logon_type": _clean_str(row.get("logon_type")),
            "auth_orientation": _clean_str(row.get("auth_orientation")),
            "success": _clean_str(row.get("success")),
            "time": float(_clean_num(row.get("time"))),
        }

        for key in [(src_c, dst_c), (src_u, dst_u)]:
            if key not in edge_map:
                edge_map[key] = (base.copy(), 0)
            edge_map[key] = (edge_map[key][0], edge_map[key][1] + 1)

    return [(src, dst, {**attrs, "weight": count}) for (src, dst), (attrs, count) in edge_map.items()]


def _build_flow_edges(flow_df: pd.DataFrame) -> list[tuple[str, str, dict]]:
    if flow_df.empty:
        return []

    edge_map: dict[tuple[str, str], tuple[dict, int]] = {}

    for _, row in flow_df.iterrows():
        src_c, dst_c = _clean_str(row.get("src_comp")), _clean_str(row.get("dst_comp"))

        base = {
            "type": "flow",
            "protocol": _clean_str(row.get("protocol")),
            "src_port": _clean_str(row.get("src_port")),
            "dst_port": _clean_str(row.get("dst_port")),
            "pkt_count": _clean_num(row.get("pkt_count")),
            "byte_count": _clean_num(row.get("byte_count")),
            "duration": _clean_num(row.get("duration")),
            "time": float(_clean_num(row.get("time"))),
        }

        key = (src_c, dst_c)
        if key not in edge_map:
            edge_map[key] = (base.copy(), 0)
        edge_map[key] = (edge_map[key][0], edge_map[key][1] + 1)

    return [(src, dst, {**attrs, "weight": count}) for (src, dst), (attrs, count) in edge_map.items()]


def build_combined_graph(auth_df: pd.DataFrame, flow_df: pd.DataFrame) -> ig.Graph:
    """Build directed graph from both auth and flow events."""
    g = ig.Graph(directed=True)
    computers, users = _collect_nodes(auth_df, flow_df)
    _add_nodes(g, computers, users)
    for src, dst, attrs in _build_auth_edges(auth_df):
        g.add_edge(src, dst, **attrs)
    for src, dst, attrs in _build_flow_edges(flow_df):
        g.add_edge(src, dst, **attrs)
    return g


def build_auth_graph(auth_df: pd.DataFrame) -> ig.Graph:
    """Build directed graph from auth events only."""
    g = ig.Graph(directed=True)
    computers, users = _collect_nodes(auth_df, pd.DataFrame())
    _add_nodes(g, computers, users)
    for src, dst, attrs in _build_auth_edges(auth_df):
        g.add_edge(src, dst, **attrs)
    return g


def build_flow_graph(flow_df: pd.DataFrame) -> ig.Graph:
    """Build directed graph from flow events only."""
    g = ig.Graph(directed=True)
    computers, users = _collect_nodes(pd.DataFrame(), flow_df)
    _add_nodes(g, computers, users)
    for src, dst, attrs in _build_flow_edges(flow_df):
        g.add_edge(src, dst, **attrs)
    return g


def get_graph_stats(g: ig.Graph) -> dict:
    """Return dict with node_count, edge_count, density, component_count."""
    return {
        "node_count": g.vcount(),
        "edge_count": g.ecount(),
        "density": g.density(),
        "component_count": len(g.connected_components()),
    }
