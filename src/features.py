"""Structural, temporal, and statistical feature extraction from igraph graphs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import igraph as ig


def extract_node_features(g: ig.Graph) -> pd.DataFrame:
    """Per-node structural and temporal features."""
    n = g.vcount()
    names = [g.vs[i]["name"] for i in range(n)]
    in_deg = g.indegree()
    out_deg = g.outdegree()
    total_deg = [in_deg[i] + out_deg[i] for i in range(n)]
    fan_out = [
        out_deg[i] / total_deg[i] if total_deg[i] > 0 else 0.0
        for i in range(n)
    ]
    betweenness = (
        g.betweenness(directed=True, normalized=True)
        if n <= 5000
        else [0.0] * n
    )

    # Temporal features: per-node outgoing edges
    inter_arr_mean = [0.0] * n
    inter_arr_std = [0.0] * n
    burst_score = [0.0] * n
    active_duration = [0.0] * n

    for i in range(n):
        out_eids = g.incident(i, mode="out")
        if not out_eids:
            continue
        times = []
        for eid in out_eids:
            t = g.es[eid].attributes().get("time")
            if t is not None:
                times.append(float(t))
        if len(times) < 2:
            continue
        times.sort()
        gaps = np.diff(times)
        inter_arr_mean[i] = float(np.mean(gaps))
        inter_arr_std[i] = float(np.std(gaps))

        # Burst score: ratio of edges in busiest 10% of time window to total
        time_span = times[-1] - times[0]
        if time_span <= 0:
            continue
        window_10pct = time_span * 0.1
        # Slide a window of size window_10pct and find max edges in any such window
        max_in_window = 0
        left = 0
        for right in range(len(times)):
            while times[right] - times[left] > window_10pct:
                left += 1
            count = right - left + 1
            if count > max_in_window:
                max_in_window = count
        burst_score[i] = max_in_window / len(times) if len(times) > 0 else 0.0
        active_duration[i] = time_span

    df = pd.DataFrame(
        {
            "in_degree": in_deg,
            "out_degree": out_deg,
            "total_degree": total_deg,
            "fan_out_ratio": fan_out,
            "betweenness_centrality": betweenness,
            "inter_arrival_mean": inter_arr_mean,
            "inter_arrival_std": inter_arr_std,
            "burst_score": burst_score,
            "active_duration": active_duration,
        },
        index=names,
    )
    df.index.name = "node"
    df = df.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    return df


def extract_edge_features(g: ig.Graph) -> pd.DataFrame:
    """Per-edge statistical features."""
    n = g.ecount()
    edge_rarity = [0.0] * n
    src_out_deg = [0] * n
    dst_in_deg = [0] * n

    out_deg_arr = g.outdegree()
    in_deg_arr = g.indegree()

    for i in range(n):
        weight = g.es[i].attributes().get("weight", 1)
        edge_rarity[i] = 1.0 / weight
        src_out_deg[i] = out_deg_arr[g.es[i].source]
        dst_in_deg[i] = in_deg_arr[g.es[i].target]

    df = pd.DataFrame(
        {
            "edge_rarity": edge_rarity,
            "src_out_degree": src_out_deg,
            "dst_in_degree": dst_in_deg,
        },
        index=pd.Index(range(n), name="edge_index"),
    )
    df = df.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    return df


def extract_graph_features(g: ig.Graph) -> dict:
    """Global graph-level features."""
    return {
        "density": g.density(),
        "avg_clustering": float(np.mean(g.to_undirected().transitivity_local_undirected(mode="zero"))),
        "component_count": len(g.connected_components(mode="weak")),
        "node_count": g.vcount(),
        "edge_count": g.ecount(),
    }


def extract_all_features(g: ig.Graph) -> dict:
    """Combine all features. Returns {'node_features': df, 'edge_features': df, 'graph_features': dict}."""
    return {
        "node_features": extract_node_features(g),
        "edge_features": extract_edge_features(g),
        "graph_features": extract_graph_features(g),
    }
