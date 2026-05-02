"""Structural, temporal, and statistical feature extraction from igraph graphs."""

from __future__ import annotations

import logging
import os
from concurrent.futures import ProcessPoolExecutor

import igraph as ig
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _compute_node_temporal(args: tuple[int, list[float]], burst_window_pct: float = 0.1) -> tuple[int, float, float, float, float]:
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

    window_10pct = time_span * burst_window_pct
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


def extract_node_features(g: ig.Graph, config: dict | None = None) -> pd.DataFrame:
    feat_cfg = (config or {}).get("features", {})
    betweenness_node_limit = feat_cfg.get("betweenness_node_limit", 5000)
    burst_window_pct = feat_cfg.get("temporal_burst_window_pct", 0.1)
    max_workers = feat_cfg.get("max_workers", 12)

    n = g.vcount()
    names = [g.vs[i]["name"] for i in range(n)]
    in_deg = g.indegree()
    out_deg = g.outdegree()
    total_deg = [in_deg[i] + out_deg[i] for i in range(n)]
    fan_out = [
        out_deg[i] / total_deg[i] if total_deg[i] > 0 else 0.0
        for i in range(n)
    ]
    approx_betweenness = feat_cfg.get("approximate_betweenness", True)
    betweenness_cutoff = feat_cfg.get("betweenness_cutoff", 3)

    if n <= betweenness_node_limit:
        betweenness = g.betweenness(directed=True, normalized=True)
    elif approx_betweenness:
        betweenness = g.betweenness(directed=True, normalized=True, cutoff=betweenness_cutoff)
    else:
        betweenness = [0.0] * n

    inter_arr_mean = [0.0] * n
    inter_arr_std = [0.0] * n
    burst_score = [0.0] * n
    active_duration = [0.0] * n

    node_times = _extract_node_times(g)
    if not node_times:
        return _build_node_df(names, in_deg, out_deg, total_deg, fan_out, betweenness,
                              inter_arr_mean, inter_arr_std, burst_score, active_duration)

    n_workers = min(os.cpu_count() or 1, max_workers)
    items = list(node_times.items())

    if n_workers <= 1 or len(items) < n_workers * 10:
        for idx, times in items:
            _, inter_arr_mean[idx], inter_arr_std[idx], burst_score[idx], active_duration[idx] = _compute_node_temporal((idx, times), burst_window_pct=burst_window_pct)
    else:
        from functools import partial
        _compute_fn = partial(_compute_node_temporal, burst_window_pct=burst_window_pct)
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            results = pool.map(_compute_fn, items)
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


def _rank_pct(values: list[float]) -> list[float]:
    """Convert values to percentile ranks (0-1). Ties get average rank."""
    arr = np.array(values, dtype=float)
    n = len(arr)
    if n == 0:
        return []
    order = np.argsort(arr)
    ranks = np.empty(n, dtype=float)
    ranks[order] = np.arange(1, n + 1, dtype=float)
    nan_mask = np.isnan(arr)
    ranks[nan_mask] = 0.0
    sorted_vals = arr[order]
    sorted_ranks = ranks[order].copy()
    i = 0
    while i < n:
        j = i + 1
        while j < n and sorted_vals[j] == sorted_vals[i]:
            j += 1
        if j - i > 1:
            avg_rank = np.mean(sorted_ranks[i:j])
            sorted_ranks[i:j] = avg_rank
        i = j
    ranks[order] = sorted_ranks
    result = (ranks - 1.0) / max(n - 1, 1)
    return result.tolist()


def extract_edge_features(g: ig.Graph, config: dict | None = None) -> pd.DataFrame:
    (config or {}).get("features", {})
    scoring_cfg = (config or {}).get("scoring", {})

    n = g.ecount()
    edge_rarity = [0.0] * n
    src_out_deg = [0] * n
    dst_in_deg = [0] * n
    is_ntlm = [0.0] * n
    is_network_logon = [0.0] * n
    is_success_auth = [0.0] * n
    source_fan_out = [0] * n
    weight_norm = [0.0] * n
    is_self_loop = [0.0] * n
    is_user_edge = [0.0] * n
    is_unusual_dst_port = [0.0] * n
    protocol_rarity = [0.0] * n
    byte_per_packet = [0.0] * n
    duration_zscore = [0.0] * n
    temporal_decay_weight = [1.0] * n

    out_deg_arr = g.outdegree()
    in_deg_arr = g.indegree()

    protocol_counts: dict[str, int] = {}
    for i in range(n):
        proto = g.es[i].attributes().get("protocol")
        if proto is not None:
            protocol_counts[proto] = protocol_counts.get(proto, 0) + 1
    total_flow_edges = sum(protocol_counts.values()) or 1

    bpp_raw = [float("nan")] * n
    for i in range(n):
        attrs = g.es[i].attributes()
        bc = attrs.get("byte_count")
        pc = attrs.get("pkt_count")
        if bc is not None and pc is not None:
            try:
                bpp_raw[i] = float(bc) / max(float(pc), 1.0)
            except (ValueError, TypeError):
                bpp_raw[i] = float("nan")
    bpp_ranks = _rank_pct(bpp_raw)

    durations_raw: list[float] = []
    for i in range(n):
        attrs = g.es[i].attributes()
        dur = attrs.get("duration")
        if dur is not None:
            try:
                durations_raw.append(float(dur))
            except (ValueError, TypeError):
                durations_raw.append(float("nan"))
    dur_arr = np.array(durations_raw, dtype=float)
    valid_durs = dur_arr[~np.isnan(dur_arr)]
    dur_mean = float(np.mean(valid_durs)) if len(valid_durs) > 0 else 0.0
    dur_std = float(np.std(valid_durs)) if len(valid_durs) > 0 else 1.0

    decay_rate = scoring_cfg.get("temporal_decay_rate", 0.0)
    edge_times: list[float] = []
    if decay_rate > 0:
        for i in range(n):
            attrs = g.es[i].attributes()
            t = attrs.get("first_time")
            if t is None:
                t = attrs.get("time")
            if t is not None:
                edge_times.append(float(t))
    if edge_times:
        max_time = max(edge_times)
        min_time = min(edge_times)
        time_span = max(max_time - min_time, 1.0)
    else:
        max_time = 0.0
        time_span = 1.0

    suspicious_ports = {22, 23, 445, 3389, 5985, 5986}

    for i in range(n):
        attrs = g.es[i].attributes()
        src_name = g.vs[g.es[i].source]["name"]
        dst_name = g.vs[g.es[i].target]["name"]

        weight = attrs.get("weight", 1)
        edge_rarity[i] = 1.0 / weight
        weight_norm[i] = 1.0 / weight
        src_out_deg[i] = out_deg_arr[g.es[i].source]
        dst_in_deg[i] = in_deg_arr[g.es[i].target]
        source_fan_out[i] = out_deg_arr[g.es[i].source]

        auth_type = attrs.get("auth_type", "")
        is_ntlm[i] = 1.0 if auth_type == "NTLM" else 0.0

        logon_type = attrs.get("logon_type", "")
        is_network_logon[i] = 1.0 if logon_type == "Network" else 0.0

        success = attrs.get("success", "")
        is_success_auth[i] = 1.0 if success == "Success" else 0.0

        is_self_loop[i] = 1.0 if g.es[i].source == g.es[i].target else 0.0

        is_user_edge[i] = 1.0 if ("@" in src_name or "@" in dst_name) else 0.0

        dp = attrs.get("dst_port")
        if dp is not None:
            try:
                dp_int = int(dp)
                is_unusual_dst_port[i] = 1.0 if (dp_int in suspicious_ports or dp_int > 49152) else 0.0
            except (ValueError, TypeError):
                is_unusual_dst_port[i] = 0.0

        proto = attrs.get("protocol")
        if proto is not None and proto in protocol_counts:
            protocol_rarity[i] = 1.0 - (protocol_counts[proto] / total_flow_edges)

        byte_per_packet[i] = bpp_ranks[i]
        if np.isnan(byte_per_packet[i]):
            byte_per_packet[i] = 0.0

        dur_val = attrs.get("duration")
        if dur_val is not None:
            try:
                d = float(dur_val)
                duration_zscore[i] = (d - dur_mean) / max(dur_std, 1e-10)
                if not np.isfinite(duration_zscore[i]):
                    duration_zscore[i] = 0.0
            except (ValueError, TypeError):
                duration_zscore[i] = 0.0

        if decay_rate <= 0:
            temporal_decay_weight[i] = 1.0
        else:
            t = attrs.get("first_time")
            if t is None:
                t = attrs.get("time")
            if t is not None:
                temporal_decay_weight[i] = float(np.exp(-decay_rate * (max_time - float(t)) / time_span))
            else:
                temporal_decay_weight[i] = 1.0

    df = pd.DataFrame(
        {
            "edge_rarity": edge_rarity,
            "src_out_degree": src_out_deg,
            "dst_in_degree": dst_in_deg,
            "is_ntlm": is_ntlm,
            "is_network_logon": is_network_logon,
            "is_success_auth": is_success_auth,
            "source_fan_out": source_fan_out,
            "weight_norm": weight_norm,
            "is_self_loop": is_self_loop,
            "is_user_edge": is_user_edge,
            "is_unusual_dst_port": is_unusual_dst_port,
            "protocol_rarity": protocol_rarity,
            "byte_per_packet": byte_per_packet,
            "duration_zscore": duration_zscore,
            "temporal_decay_weight": temporal_decay_weight,
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


def extract_all_features(g: ig.Graph, config: dict | None = None) -> dict:
    return {
        "node_features": extract_node_features(g, config=config),
        "edge_features": extract_edge_features(g, config=config),
        "graph_features": extract_graph_features(g),
    }
