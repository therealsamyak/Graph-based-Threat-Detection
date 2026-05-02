"""Anomaly scoring for multi-hop paths in igraph graphs."""

from __future__ import annotations

import logging
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

import igraph as ig
import numpy as np
import pandas as pd

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


def _enumerate_paths_for_nodes(
    adjacency: dict[int, list[tuple[int, int]]],
    edge_scores_arr: np.ndarray,
    node_names: list[str],
    edge_targets: np.ndarray,
    node_indices: list[int],
    max_hops: int,
) -> list[dict]:
    """BFS path enumeration for a subset of nodes. Returns list of path dicts."""
    all_paths: list[dict] = []

    for src_idx in node_indices:
        scored_out = adjacency.get(src_idx, [])
        if not scored_out:
            continue

        queue: deque[tuple[int, list[int], set[int]]] = deque()
        for eid, dst in scored_out:
            queue.append((dst, [eid], {src_idx, dst}))

        while queue:
            node, path_edges, visited = queue.popleft()
            path_len = len(path_edges)
            if path_len > max_hops:
                continue

            escores = [edge_scores_arr[eid] for eid in path_edges]
            product = float(np.prod(escores)) if escores else 0.0
            max_s = float(np.max(escores)) if escores else 0.0
            mean_s = float(np.mean(escores)) if escores else 0.0
            path_score = (product + max_s + mean_s) / 3.0

            path_nodes = [node_names[src_idx]]
            for eid in path_edges:
                path_nodes.append(node_names[edge_targets[eid]])

            all_paths.append({
                "source_node": node_names[src_idx],
                "path_score": path_score,
                "path_nodes": path_nodes,
                "path_edges": path_edges,
                "path_length": path_len,
            })

            if path_len < max_hops:
                next_scored = adjacency.get(node, [])
                for eid, dst in next_scored:
                    if dst not in visited:
                        queue.append((dst, path_edges + [eid], visited | {dst}))

    return all_paths


def _compute_edge_source_stats_chunk(edge_data: list[tuple[int, str, str, str]]) -> tuple[dict[int, int], dict[int, int], dict[int, set[str]], dict[int, int]]:
    """Process a chunk of edges, return partial counts."""
    src_auth_failures: dict[int, int] = {}
    src_auth_total: dict[int, int] = {}
    src_ports: dict[int, set[str]] = {}
    src_flow_total: dict[int, int] = {}

    for src, edge_type, success, dst_port in edge_data:
        if edge_type == "auth":
            src_auth_total[src] = src_auth_total.get(src, 0) + 1
            if success != "1":
                src_auth_failures[src] = src_auth_failures.get(src, 0) + 1
        elif edge_type == "flow":
            src_flow_total[src] = src_flow_total.get(src, 0) + 1
            if src not in src_ports:
                src_ports[src] = set()
            src_ports[src].add(dst_port)

    return src_auth_failures, src_auth_total, src_ports, src_flow_total


def _compute_edge_source_stats(g: ig.Graph) -> tuple[list[float], list[float]]:
    """Single-pass computation of auth_failure_rate and port_diversity per edge."""
    n = g.ecount()

    # Extract edge data to plain Python tuples (no igraph refs) for pickling
    edge_data: list[tuple[int, str, str, str]] = []
    for i in range(n):
        attrs = g.es[i].attributes()
        src = g.es[i].source
        edge_data.append((src, attrs.get("type", ""), attrs.get("success", ""), str(attrs.get("dst_port", ""))))

    sources = [ed[0] for ed in edge_data]

    PARALLEL_THRESHOLD = 100_000

    if n > PARALLEL_THRESHOLD and (os.cpu_count() or 1) > 1:
        n_workers = min(os.cpu_count() or 1, 12)
        chunk_size = (n + n_workers - 1) // n_workers
        chunks = [edge_data[i * chunk_size : (i + 1) * chunk_size] for i in range(n_workers)]

        src_auth_failures: dict[int, int] = {}
        src_auth_total: dict[int, int] = {}
        src_ports: dict[int, set[str]] = {}
        src_flow_total: dict[int, int] = {}

        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            results = pool.map(_compute_edge_source_stats_chunk, chunks)
            for partial_af, partial_at, partial_p, partial_ft in results:
                for k, v in partial_af.items():
                    src_auth_failures[k] = src_auth_failures.get(k, 0) + v
                for k, v in partial_at.items():
                    src_auth_total[k] = src_auth_total.get(k, 0) + v
                for k, v in partial_p.items():
                    if k not in src_ports:
                        src_ports[k] = set()
                    src_ports[k].update(v)
                for k, v in partial_ft.items():
                    src_flow_total[k] = src_flow_total.get(k, 0) + v
    else:
        src_auth_failures, src_auth_total, src_ports, src_flow_total = _compute_edge_source_stats_chunk(edge_data)

    src_failure_rate = {src: src_auth_failures.get(src, 0) / total for src, total in src_auth_total.items()}
    src_diversity = {src: len(src_ports[src]) / total for src, total in src_flow_total.items() if total > 0}

    auth_fail = [src_failure_rate.get(sources[i], 0.0) for i in range(n)]
    port_div = [src_diversity.get(sources[i], 0.0) for i in range(n)]

    return auth_fail, port_div


def _minmax_scale(values: list[float]) -> list[float]:
    """Min-max scale to [0,1]. Returns all 0s if all values identical."""
    if not values:
        return []
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
    auth_fail, port_div = _compute_edge_source_stats(g)

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
    total_nodes = g.vcount()
    n_workers = min(os.cpu_count() or 1, 12)
    edge_scores_arr = edge_scores.values

    node_names = [g.vs[i]["name"] for i in range(total_nodes)]
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for src in range(total_nodes):
        out_eids = g.incident(src, mode="out")
        if out_eids:
            scored = sorted(out_eids, key=lambda eid: edge_scores_arr[eid], reverse=True)[:10]
            adjacency[src] = [(eid, g.es[eid].target) for eid in scored]

    edge_targets = np.array([g.es[i].target for i in range(g.ecount())])

    if n_workers <= 1 or total_nodes < n_workers * 10:
        all_paths = _enumerate_paths_for_nodes(
            adjacency, edge_scores_arr, node_names, edge_targets, list(range(total_nodes)), max_hops,
        )
    else:
        chunk_size = total_nodes // n_workers
        node_chunks = [
            list(range(i * chunk_size, min((i + 1) * chunk_size, total_nodes)))
            for i in range(n_workers)
        ]
        if node_chunks and node_chunks[-1][-1] < total_nodes - 1:
            node_chunks[-1].extend(range(node_chunks[-1][-1] + 1, total_nodes))

        logger.info(
            f"    Parallel path enumeration: {total_nodes:,} nodes across {n_workers} workers"
        )

        all_paths: list[dict] = []
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            futures = [
                pool.submit(_enumerate_paths_for_nodes, adjacency, edge_scores_arr, node_names, edge_targets, chunk, max_hops)
                for chunk in node_chunks
            ]
            done_count = 0
            for future in futures:
                result = future.result()
                all_paths.extend(result)
                done_count += 1
                logger.info(
                    f"    Path enumeration: worker {done_count}/{n_workers} done, "
                    f"{len(all_paths):,} paths so far"
                )

    if not all_paths:
        return pd.DataFrame(columns=["source_node", "path_score", "path_nodes", "path_edges", "path_length"])

    df = pd.DataFrame(all_paths)
    df = df.sort_values("path_score", ascending=False).head(top_k).reset_index(drop=True)
    return df


def score_graph(
    g: ig.Graph,
    all_features: dict,
    edge_scores: pd.Series | None = None,
    paths: pd.DataFrame | None = None,
    threshold: float = 0.5,
) -> dict:
    """Aggregate graph-level anomaly scores."""
    edge_features = all_features["edge_features"]

    if edge_scores is None:
        edge_scores = score_edges(g, edge_features)

    if paths is None:
        paths = score_paths(g, edge_scores)

    return {
        "max_path_score": float(paths["path_score"].max()) if len(paths) > 0 else 0.0,
        "mean_path_score": float(paths["path_score"].mean()) if len(paths) > 0 else 0.0,
        "anomalous_path_count": int((paths["path_score"] > threshold).sum()) if len(paths) > 0 else 0,
        "max_edge_score": float(edge_scores.max()) if len(edge_scores) > 0 else 0.0,
        "mean_edge_score": float(edge_scores.mean()) if len(edge_scores) > 0 else 0.0,
        "high_rarity_edge_count": int((edge_features["edge_rarity"] > 0.5).sum()),
    }
