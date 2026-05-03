"""Structural, temporal, and statistical feature extraction from igraph graphs."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor

import igraph as ig
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _compute_node_temporal(args: tuple[int, list[float]]) -> tuple[int, float, float, float, float]:
    node_idx, times = args
    if len(times) < 2:
        return node_idx, 0.0, 0.0, 0.0, 0.0

    times.sort()
    gaps = np.diff(times)
    inter_arr_mean = float(np.mean(gaps))
    inter_arr_std = float(np.std(gaps))

    time_span = times[-1] - times[0]
    if time_span <= 0:
        return node_idx, inter_arr_mean, inter_arr_std, 0.0, 0.0

    window_10pct = time_span * 0.1
    max_in_window = 0
    left = 0
    for right in range(len(times)):
        while times[right] - times[left] > window_10pct:
            left += 1
        count = right - left + 1
        if count > max_in_window:
            max_in_window = count

    burst = max_in_window / len(times)
    return node_idx, inter_arr_mean, inter_arr_std, burst, time_span


def _extract_node_times(g: ig.Graph) -> dict[int, list[float]]:
    n = g.vcount()
    node_times: dict[int, list[float]] = {}
    for i in range(n):
        out_eids = g.incident(i, mode="out")
        if not out_eids:
            continue
        times = []
        for eid in out_eids:
            t = g.es[eid].attributes().get("time")
            if t is not None:
                times.append(float(t))
        if times:
            node_times[i] = times
    return node_times


def extract_node_features(g: ig.Graph) -> pd.DataFrame:
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
        else g.betweenness(directed=True, normalized=True, cutoff=3)
    )

    inter_arr_mean = [0.0] * n
    inter_arr_std = [0.0] * n
    burst_score = [0.0] * n
    active_duration = [0.0] * n

    node_times = _extract_node_times(g)
    if not node_times:
        return _build_node_df(names, in_deg, out_deg, total_deg, fan_out, betweenness,
                              inter_arr_mean, inter_arr_std, burst_score, active_duration)

    n_workers = min(os.cpu_count() or 1, 12)
    items = list(node_times.items())

    if n_workers <= 1 or len(items) < n_workers * 10:
        for idx, times in items:
            _, inter_arr_mean[idx], inter_arr_std[idx], burst_score[idx], active_duration[idx] = _compute_node_temporal((idx, times))
    else:
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            results = pool.map(_compute_node_temporal, items)
            for idx, iam, ias, bs, ad in results:
                inter_arr_mean[idx] = iam
                inter_arr_std[idx] = ias
                burst_score[idx] = bs
                active_duration[idx] = ad

    return _build_node_df(names, in_deg, out_deg, total_deg, fan_out, betweenness,
                          inter_arr_mean, inter_arr_std, burst_score, active_duration)


def _build_node_df(names, in_deg, out_deg, total_deg, fan_out, betweenness,
                   inter_arr_mean, inter_arr_std, burst_score, active_duration) -> pd.DataFrame:
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


# Lateral movement ports per LaTeX Section 4.2
LATERAL_MOVEMENT_PORTS = {22, 23, 445, 3389, 5985, 5986}
EPHEMERAL_PORT_THRESHOLD = 49152


def extract_edge_features(g: ig.Graph) -> pd.DataFrame:
    """Extract 12 edge features as described in LaTeX Section 4.2.

    For all edges: edge_rarity, src_out_degree, dst_in_degree, src_fan_out,
        normalized_weight, is_self_loop, is_user_edge.
    For auth edges: is_ntlm, is_network_logon, auth_success.
    For flow edges: is_unusual_dst_port, is_ephemeral, protocol_rarity,
        byte_per_packet_ratio, duration_z_score.
    """
    n = g.ecount()
    if n == 0:
        return pd.DataFrame(index=pd.Index([], name="edge_index"))

    out_deg_arr = g.outdegree()
    in_deg_arr = g.indegree()
    total_deg_arr = [out_deg_arr[i] + in_deg_arr[i] for i in range(g.vcount())]

    # --- Common features for all edges ---
    edge_rarity = [0.0] * n
    src_out_deg = [0] * n
    dst_in_deg = [0] * n
    src_fan_out = [0.0] * n
    normalized_weight = [0.0] * n
    is_self_loop = [0] * n
    is_user_edge = [0] * n

    # --- Auth-specific features ---
    is_ntlm = [0] * n
    is_network_logon = [0] * n
    auth_success = [0] * n

    # --- Flow-specific features ---
    is_unusual_dst_port = [0] * n
    is_ephemeral = [0] * n
    protocol_rarity = [0.0] * n
    byte_per_packet_ratio = [0.0] * n
    duration_z_score = [0.0] * n

    # Collect protocol counts for protocol_rarity
    protocol_counts: dict[str, int] = {}
    # Collect byte_per_packet and duration for z-score computation
    bpp_values: list[float] = []
    duration_values: list[float] = []

    for i in range(n):
        e = g.es[i]
        attrs = e.attributes()
        weight = attrs.get("weight", 1)
        edge_rarity[i] = 1.0 / weight
        src_idx = e.source
        dst_idx = e.target
        src_out_deg[i] = out_deg_arr[src_idx]
        dst_in_deg[i] = in_deg_arr[dst_idx]

        # src_fan_out
        src_total = total_deg_arr[src_idx]
        src_fan_out[i] = out_deg_arr[src_idx] / src_total if src_total > 0 else 0.0

        # is_self_loop
        is_self_loop[i] = 1 if src_idx == dst_idx else 0

        # is_user_edge
        src_type = g.vs[src_idx].get("node_type", "computer")
        dst_type = g.vs[dst_idx].get("node_type", "computer")
        is_user_edge[i] = 1 if src_type == "user" or dst_type == "user" else 0

        edge_type = attrs.get("type", "")

        if edge_type == "auth":
            auth_t = str(attrs.get("auth_type", "")).upper()
            is_ntlm[i] = 1 if "NTLM" in auth_t else 0
            logon_t = str(attrs.get("logon_type", "")).lower()
            is_network_logon[i] = 1 if "network" in logon_t else 0
            success = str(attrs.get("success", "")).lower()
            auth_success[i] = 1 if success in ("true", "1", "yes") else 0
        elif edge_type == "flow":
            dst_port = attrs.get("dst_port", 0)
            try:
                dst_port_int = int(float(dst_port))
            except (ValueError, TypeError):
                dst_port_int = 0
            is_unusual_dst_port[i] = 1 if dst_port_int in LATERAL_MOVEMENT_PORTS else 0
            is_ephemeral[i] = 1 if dst_port_int >= EPHEMERAL_PORT_THRESHOLD else 0

            proto = str(attrs.get("protocol", ""))
            protocol_counts[proto] = protocol_counts.get(proto, 0) + 1

            pkt = float(attrs.get("pkt_count", 0) or 0)
            byt = float(attrs.get("byte_count", 0) or 0)
            bpp_values.append(byt / pkt if pkt > 0 else 0.0)

            dur = float(attrs.get("duration", 0) or 0)
            duration_values.append(dur)

    # Compute normalized_weight (percentile rank of weight)
    weights = [g.es[i].attributes().get("weight", 1) for i in range(n)]
    if weights:
        sorted_w = sorted(set(weights))
        rank_map = {w: i / max(len(sorted_w) - 1, 1) for i, w in enumerate(sorted_w)}
        normalized_weight = [rank_map.get(w, 0.5) for w in weights]

    # Compute protocol_rarity: 1 - proportion of edges using that protocol
    total_flow_edges = sum(protocol_counts.values())
    protocol_rarity_map = {}
    if total_flow_edges > 0:
        for proto, count in protocol_counts.items():
            protocol_rarity_map[proto] = 1.0 - (count / total_flow_edges)

    # Compute byte_per_packet_ratio as percentile rank
    if bpp_values:
        bpp_sorted = sorted(bpp_values)
        bpp_rank_map = {}
        for idx, val in enumerate(bpp_sorted):
            bpp_rank_map[val] = idx / max(len(bpp_sorted) - 1, 1)
        bpp_idx = 0
        for i in range(n):
            if g.es[i].attributes().get("type", "") == "flow":
                pkt = float(g.es[i].attributes().get("pkt_count", 0) or 0)
                byt = float(g.es[i].attributes().get("byte_count", 0) or 0)
                bpp = byt / pkt if pkt > 0 else 0.0
                byte_per_packet_ratio[i] = bpp_rank_map.get(bpp, 0.5)
                bpp_idx += 1

    # Compute duration z-score
    if duration_values and len(duration_values) > 1:
        dur_arr = np.array(duration_values)
        dur_mean = float(np.mean(dur_arr))
        dur_std = float(np.std(dur_arr))
        if dur_std > 0:
            dur_zscores = ((dur_arr - dur_mean) / dur_std).tolist()
        else:
            dur_zscores = [0.0] * len(dur_arr)
        dur_idx = 0
        for i in range(n):
            if g.es[i].attributes().get("type", "") == "flow":
                duration_z_score[i] = dur_zscores[dur_idx] if dur_idx < len(dur_zscores) else 0.0
                dur_idx += 1

    # Fill protocol_rarity for flow edges
    for i in range(n):
        if g.es[i].attributes().get("type", "") == "flow":
            proto = str(g.es[i].attributes().get("protocol", ""))
            protocol_rarity[i] = protocol_rarity_map.get(proto, 0.5)

    # Build DataFrame
    df = pd.DataFrame(
        {
            "edge_rarity": edge_rarity,
            "src_out_degree": src_out_deg,
            "dst_in_degree": dst_in_deg,
            "src_fan_out": src_fan_out,
            "normalized_weight": normalized_weight,
            "is_self_loop": is_self_loop,
            "is_user_edge": is_user_edge,
            "is_ntlm": is_ntlm,
            "is_network_logon": is_network_logon,
            "auth_success": auth_success,
            "is_unusual_dst_port": is_unusual_dst_port,
            "is_ephemeral": is_ephemeral,
            "protocol_rarity": protocol_rarity,
            "byte_per_packet_ratio": byte_per_packet_ratio,
            "duration_z_score": duration_z_score,
        },
        index=pd.Index(range(n), name="edge_index"),
    )
    df = df.replace([float("inf"), float("-inf")], 0.0).fillna(0.0)
    return df


def extract_graph_features(g: ig.Graph) -> dict:
    if g.vcount() == 0:
        return {
            "density": 0.0,
            "avg_clustering": 0.0,
            "component_count": 0,
            "node_count": 0,
            "edge_count": 0,
        }
    ug = g.copy()
    ug.to_undirected()
    clustering = ug.transitivity_local_undirected(mode="zero")
    return {
        "density": g.density(),
        "avg_clustering": float(np.mean(clustering)) if clustering else 0.0,
        "component_count": len(g.connected_components(mode="weak")),
        "node_count": g.vcount(),
        "edge_count": g.ecount(),
    }


def extract_all_features(g: ig.Graph) -> dict:
    return {
        "node_features": extract_node_features(g),
        "edge_features": extract_edge_features(g),
        "graph_features": extract_graph_features(g),
    }
