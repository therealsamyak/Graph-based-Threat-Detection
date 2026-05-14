"""Edge-level feature extraction: rarity, protocol, duration, temporal decay."""

from __future__ import annotations

import igraph as ig
import numpy as np
import pandas as pd


def _rank_pct(values: np.ndarray) -> np.ndarray:
    arr = values.astype(float).copy()
    n = len(arr)
    if n == 0:
        return arr
    valid = ~np.isnan(arr)
    order = np.argsort(arr[valid])
    ranks = np.empty(order.shape[0], dtype=float)
    ranks[order] = np.arange(1, order.shape[0] + 1, dtype=float)
    sorted_vals = arr[valid][order]
    sorted_ranks = ranks.copy()
    i = 0
    while i < len(sorted_vals):
        j = i + 1
        while j < len(sorted_vals) and sorted_vals[j] == sorted_vals[i]:
            j += 1
        if j - i > 1:
            avg_rank = np.mean(sorted_ranks[i:j])
            sorted_ranks[i:j] = avg_rank
        i = j
    ranks[order] = sorted_ranks
    result = np.zeros(n, dtype=float)
    result[valid] = (ranks - 1.0) / max(order.shape[0] - 1, 1)
    return result


def _get_edge_attr_array(g: ig.Graph, attr: str, default=None) -> list:
    try:
        return g.es[attr]
    except (KeyError, AttributeError):
        return [default] * g.ecount()


def extract_edge_features(g: ig.Graph, config: dict | None = None) -> pd.DataFrame:
    scoring_cfg = (config or {}).get("scoring", {})

    n = g.ecount()
    if n == 0:
        return pd.DataFrame(
            {
                "edge_rarity": pd.Series(dtype=float),
                "src_out_degree": pd.Series(dtype=float),
                "dst_in_degree": pd.Series(dtype=float),
                "dst_fan_out_ratio": pd.Series(dtype=float),
                "is_ntlm": pd.Series(dtype=float),
                "is_network_logon": pd.Series(dtype=float),
                "is_success_auth": pd.Series(dtype=float),
                "source_fan_out": pd.Series(dtype=float),
                "weight_norm": pd.Series(dtype=float),
                "is_self_loop": pd.Series(dtype=float),
                "is_user_edge": pd.Series(dtype=float),
                "is_unusual_dst_port": pd.Series(dtype=float),
                "protocol_rarity": pd.Series(dtype=float),
                "byte_per_packet": pd.Series(dtype=float),
                "duration_zscore": pd.Series(dtype=float),
                "temporal_decay_weight": pd.Series(dtype=float),
            },
            index=pd.Index([], name="edge_index", dtype=int),
        )

    out_deg = np.array(g.outdegree(), dtype=float)
    in_deg = np.array(g.indegree(), dtype=float)

    weights = np.array(_get_edge_attr_array(g, "weight", 1), dtype=float)
    edge_rarity = np.where(weights > 0, 1.0 / weights, 0.0)
    finite_weights = np.where(np.isfinite(weights), weights, 0.0)
    max_w = finite_weights.max() if finite_weights.size else 0.0
    weight_norm = finite_weights / max_w if max_w > 0 else np.zeros_like(weights)

    sources = np.array([e.source for e in g.es], dtype=int)
    targets = np.array([e.target for e in g.es], dtype=int)

    src_out_deg = out_deg[sources]
    dst_in_deg = in_deg[targets]
    total_deg = out_deg + in_deg
    source_fan_out = np.where(
        total_deg[sources] > 0, out_deg[sources] / total_deg[sources], 0.0
    )
    dst_fan_out_ratio = np.where(
        total_deg[targets] > 0, out_deg[targets] / total_deg[targets], 0.0
    )

    is_self_loop = (sources == targets).astype(float)

    vertex_names = g.vs["name"]
    src_names = [vertex_names[s] for s in sources]
    dst_names = [vertex_names[t] for t in targets]
    is_user_edge = np.array(
        [1.0 if ("@" in sn or "@" in dn) else 0.0 for sn, dn in zip(src_names, dst_names)],
        dtype=float,
    )

    auth_types = _get_edge_attr_array(g, "auth_type", "")
    is_ntlm = np.array([1.0 if at == "NTLM" else 0.0 for at in auth_types], dtype=float)

    logon_types = _get_edge_attr_array(g, "logon_type", "")
    is_network_logon = np.array([1.0 if lt == "Network" else 0.0 for lt in logon_types], dtype=float)

    successes = _get_edge_attr_array(g, "success", "")
    is_success_auth = np.array([1.0 if s == "Success" else 0.0 for s in successes], dtype=float)

    suspicious_ports = {22, 23, 445, 3389, 5985, 5986}
    dst_ports = _get_edge_attr_array(g, "dst_port", None)
    is_unusual_dst_port = np.zeros(n, dtype=float)
    for i, dp in enumerate(dst_ports):
        if dp is not None:
            try:
                dp_int = int(dp)
                if dp_int in suspicious_ports or dp_int > 49152:
                    is_unusual_dst_port[i] = 1.0
            except (ValueError, TypeError):
                pass

    protocols = _get_edge_attr_array(g, "protocol", None)
    protocol_counts: dict[str, int] = {}
    for p in protocols:
        if p is not None:
            protocol_counts[p] = protocol_counts.get(p, 0) + 1
    total_flow_edges = sum(protocol_counts.values()) or 1
    protocol_rarity = np.zeros(n, dtype=float)
    for i, p in enumerate(protocols):
        if p is not None and p in protocol_counts:
            protocol_rarity[i] = 1.0 - (protocol_counts[p] / total_flow_edges)

    byte_counts = _get_edge_attr_array(g, "byte_count", None)
    pkt_counts = _get_edge_attr_array(g, "pkt_count", None)
    bpp_raw = np.full(n, np.nan, dtype=float)
    for i in range(n):
        bc, pc = byte_counts[i], pkt_counts[i]
        if bc is not None and pc is not None:
            try:
                bpp_raw[i] = float(bc) / max(float(pc), 1.0)
            except (ValueError, TypeError):
                pass
    bpp_ranks = _rank_pct(bpp_raw)
    byte_per_packet = np.where(np.isnan(bpp_ranks), 0.0, bpp_ranks)

    durations = _get_edge_attr_array(g, "duration", None)
    dur_raw = np.full(n, np.nan, dtype=float)
    for i, d in enumerate(durations):
        if d is not None:
            try:
                dur_raw[i] = float(d)
            except (ValueError, TypeError):
                pass
    valid_durs = dur_raw[~np.isnan(dur_raw)]
    dur_mean = float(np.mean(valid_durs)) if len(valid_durs) > 0 else 0.0
    dur_std = float(np.std(valid_durs)) if len(valid_durs) > 0 else 1.0
    duration_zscore = np.where(
        ~np.isnan(dur_raw),
        (dur_raw - dur_mean) / max(dur_std, 1e-10),
        0.0,
    )
    duration_zscore = np.where(np.isfinite(duration_zscore), duration_zscore, 0.0)

    decay_rate = scoring_cfg.get("temporal_decay_rate", 0.0)
    temporal_decay_weight = np.ones(n, dtype=float)
    if decay_rate > 0:
        first_times = _get_edge_attr_array(g, "first_time", None)
        times = _get_edge_attr_array(g, "time", None)
        edge_times = np.full(n, np.nan, dtype=float)
        for i in range(n):
            t = first_times[i] if first_times[i] is not None else times[i]
            if t is not None:
                edge_times[i] = float(t)
        valid_times = edge_times[~np.isnan(edge_times)]
        if len(valid_times) > 0:
            max_time = float(np.max(valid_times))
            min_time = float(np.min(valid_times))
            time_span = max(max_time - min_time, 1.0)
            temporal_decay_weight = np.where(
                ~np.isnan(edge_times),
                np.exp(-decay_rate * (max_time - edge_times) / time_span),
                1.0,
            )

    df = pd.DataFrame(
        {
            "edge_rarity": edge_rarity,
            "src_out_degree": src_out_deg,
            "dst_in_degree": dst_in_deg,
            "dst_fan_out_ratio": dst_fan_out_ratio,
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
