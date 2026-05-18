"""Node-level feature extraction: degree, betweenness, temporal burst."""

from __future__ import annotations

import logging
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


def extract_node_features(g: ig.Graph, config: dict | None = None, variant_name: str | None = None) -> pd.DataFrame:
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

    logger.info(f"Node features: {max_workers} workers{f' (variant: {variant_name})' if variant_name else ''}")
    items = list(node_times.items())

    if max_workers <= 1 or len(items) < max_workers * 10:
        for idx, times in items:
            _, inter_arr_mean[idx], inter_arr_std[idx], burst_score[idx], active_duration[idx] = _compute_node_temporal((idx, times), burst_window_pct=burst_window_pct)
    else:
        from functools import partial
        _compute_fn = partial(_compute_node_temporal, burst_window_pct=burst_window_pct)
        with ProcessPoolExecutor(max_workers=max_workers) as pool:
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
