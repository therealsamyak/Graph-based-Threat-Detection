"""Edge-level feature extraction: rarity, protocol, duration, temporal decay."""

from __future__ import annotations

import igraph as ig
import numpy as np
import pandas as pd


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


def _compute_protocol_stats(
    n: int,
    g: ig.Graph,
) -> tuple[dict[str, int], int]:
    """Compute protocol frequency counts and total flow edges."""
    protocol_counts: dict[str, int] = {}
    for i in range(n):
        proto = g.es[i].attributes().get("protocol")
        if proto is not None:
            protocol_counts[proto] = protocol_counts.get(proto, 0) + 1
    total_flow_edges = sum(protocol_counts.values()) or 1
    return protocol_counts, total_flow_edges


def _compute_bpp_ranks(
    n: int,
    g: ig.Graph,
) -> tuple[list[float], list[float]]:
    """Compute raw bytes-per-packet and their percentile ranks."""
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
    return bpp_raw, bpp_ranks


def _compute_duration_stats(
    n: int,
    g: ig.Graph,
) -> tuple[float, float]:
    """Compute mean and std of edge durations."""
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
    return dur_mean, dur_std


def _compute_temporal_decay_params(
    n: int,
    g: ig.Graph,
    scoring_cfg: dict,
) -> tuple[float, float, list[float]]:
    """Compute temporal decay parameters: max_time, time_span, edge_times."""
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
    return max_time, time_span, edge_times


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

    protocol_counts, total_flow_edges = _compute_protocol_stats(n, g)
    _bpp_raw, bpp_ranks = _compute_bpp_ranks(n, g)
    dur_mean, dur_std = _compute_duration_stats(n, g)
    max_time, time_span, _edge_times = _compute_temporal_decay_params(n, g, scoring_cfg)

    decay_rate = scoring_cfg.get("temporal_decay_rate", 0.0)
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
