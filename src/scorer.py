"""Anomaly scoring for multi-hop paths in igraph graphs."""

from __future__ import annotations

import logging
from collections import deque

import igraph as ig
import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _compute_auth_failure_rate(g: ig.Graph) -> list[float]:
    """Fraction of auth edges from same source with success != '1'."""
    n = g.ecount()
    result = [0.0] * n

    src_auth: dict[int, list[int]] = {}
    for i in range(n):
        if g.es[i].attributes().get("type") == "auth":
            src = g.es[i].source
            src_auth.setdefault(src, []).append(i)

    src_failure_rate: dict[int, float] = {}
    for src, eids in src_auth.items():
        if not eids:
            src_failure_rate[src] = 0.0
            continue
        failures = sum(1 for eid in eids if g.es[eid].attributes().get("success") != "1")
        src_failure_rate[src] = failures / len(eids)

    for i in range(n):
        src = g.es[i].source
        result[i] = src_failure_rate.get(src, 0.0)

    return result


def _compute_port_diversity(g: ig.Graph) -> list[float]:
    """Normalized unique dst_port count from flow edges of same source."""
    n = g.ecount()
    result = [0.0] * n

    src_ports: dict[int, list[str]] = {}
    for i in range(n):
        if g.es[i].attributes().get("type") == "flow":
            src = g.es[i].source
            port = str(g.es[i].attributes().get("dst_port", ""))
            src_ports.setdefault(src, []).append(port)

    src_diversity: dict[int, float] = {}
    for src, ports in src_ports.items():
        if not ports:
            src_diversity[src] = 0.0
            continue
        src_diversity[src] = len(set(ports)) / len(ports)

    for i in range(n):
        src = g.es[i].source
        result[i] = src_diversity.get(src, 0.0)

    return result


def _minmax_scale(values: list[float]) -> list[float]:
    """Min-max scale to [0,1]. Returns all 0s if all values identical."""
    arr = np.array(values, dtype=float)
    mn, mx = arr.min(), arr.max()
    if mx - mn < 1e-12:
        return [0.0] * len(values)
    return ((arr - mn) / (mx - mn)).tolist()


def score_edges(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """Score edges via weighted combo of rarity, auth failure, port diversity.

    Returns pd.Series indexed by edge index (int), values in [0,1].
    """
    if weights is None:
        weights = {"edge_rarity": 1 / 3, "auth_failure_rate": 1 / 3, "port_diversity": 1 / 3}

    n = g.ecount()
    edge_rarity = edge_features["edge_rarity"].tolist()
    auth_fail = _compute_auth_failure_rate(g)
    port_div = _compute_port_diversity(g)

    w_r = weights.get("edge_rarity", 1 / 3)
    w_a = weights.get("auth_failure_rate", 1 / 3)
    w_p = weights.get("port_diversity", 1 / 3)
    w_total = w_r + w_a + w_p

    raw = [
        (w_r * edge_rarity[i] + w_a * auth_fail[i] + w_p * port_div[i]) / w_total
        for i in range(n)
    ]

    scaled = _minmax_scale(raw)
    return pd.Series(scaled, index=pd.Index(range(n), name="edge_index"))


def score_paths(
    g: ig.Graph,
    edge_scores: pd.Series,
    max_hops: int = 4,
    top_k: int = 50,
) -> pd.DataFrame:
    """BFS path enumeration with anomaly scoring.

    Limits outgoing exploration to top-10 edges by score per node.
    Returns DataFrame sorted by path_score descending, limited to top_k.
    Columns: source_node, path_score, path_nodes, path_edges, path_length.
    """
    all_paths: list[dict] = []
    total_nodes = g.vcount()
    log_every = max(total_nodes // 10, 1)

    for src_idx in range(total_nodes):
        if src_idx % log_every == 0 and src_idx > 0:
            logger.info(f"    Path enumeration: {src_idx}/{total_nodes} nodes processed, {len(all_paths):,} paths found...")
        out_eids = g.incident(src_idx, mode="out")
        if not out_eids:
            continue

        scored_out = sorted(out_eids, key=lambda eid: edge_scores.iloc[eid], reverse=True)[:10]

        queue: deque[tuple[int, list[int], set[int]]] = deque()
        for eid in scored_out:
            dst = g.es[eid].target
            queue.append((dst, [eid], {src_idx, dst}))

        while queue:
            node, path_edges, visited = queue.popleft()
            path_len = len(path_edges)
            if path_len > max_hops:
                continue

            escores = [edge_scores.iloc[eid] for eid in path_edges]
            product = float(np.prod(escores)) if escores else 0.0
            max_s = float(np.max(escores)) if escores else 0.0
            mean_s = float(np.mean(escores)) if escores else 0.0
            path_score = (product + max_s + mean_s) / 3.0

            path_nodes = [g.vs[src_idx]["name"]]
            for eid in path_edges:
                path_nodes.append(g.es[eid].target_vertex["name"])

            all_paths.append({
                "source_node": g.vs[src_idx]["name"],
                "path_score": path_score,
                "path_nodes": path_nodes,
                "path_edges": path_edges,
                "path_length": path_len,
            })

            if path_len < max_hops:
                next_eids = g.incident(node, mode="out")
                next_scored = sorted(next_eids, key=lambda eid: edge_scores.iloc[eid], reverse=True)[:10]
                for eid in next_scored:
                    dst = g.es[eid].target
                    if dst not in visited:
                        queue.append((dst, path_edges + [eid], visited | {dst}))

    if not all_paths:
        return pd.DataFrame(columns=["source_node", "path_score", "path_nodes", "path_edges", "path_length"])

    df = pd.DataFrame(all_paths)
    df = df.sort_values("path_score", ascending=False).head(top_k).reset_index(drop=True)
    return df


def score_graph(
    g: ig.Graph,
    all_features: dict,
    edge_scores: pd.Series | None = None,
    threshold: float = 0.5,
) -> dict:
    """Aggregate graph-level anomaly scores."""
    edge_features = all_features["edge_features"]

    if edge_scores is None:
        edge_scores = score_edges(g, edge_features)

    paths = score_paths(g, edge_scores)

    return {
        "max_path_score": float(paths["path_score"].max()) if len(paths) > 0 else 0.0,
        "mean_path_score": float(paths["path_score"].mean()) if len(paths) > 0 else 0.0,
        "anomalous_path_count": int((paths["path_score"] > threshold).sum()) if len(paths) > 0 else 0,
        "max_edge_score": float(edge_scores.max()),
        "mean_edge_score": float(edge_scores.mean()),
        "high_rarity_edge_count": int((edge_features["edge_rarity"] > 0.5).sum()),
    }
