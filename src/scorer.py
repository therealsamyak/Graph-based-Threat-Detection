"""Anomaly scoring for multi-hop paths in igraph graphs."""

from __future__ import annotations

import logging
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import igraph as ig
import numpy as np
import pandas as pd

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
            if escores:
                log_scores = np.log(np.clip(escores, 1e-10, None))
                geo_mean = float(np.exp(np.mean(log_scores)))
                max_s = float(np.max(escores))
                mean_s = float(np.mean(escores))
            else:
                geo_mean = max_s = mean_s = 0.0
            path_score = (geo_mean + max_s + mean_s) / 3.0

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


def score_edges(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    weights: dict[str, float] | None = None,
    config: dict | None = None,
) -> pd.Series:
    """Score edges via discriminative features: NTLM, network logon, edge rarity.

    Edges where either endpoint contains "@" (user edges) or where src == dst
    (self-loops) receive score 0.0 — these have zero red-team signal.
    Auth edges use weighted combo of NTLM, network logon, and rarity rank;
    flow edges use flow-specific features (rarity, unusual dst port, protocol rarity).
    Optionally applies auth_weight_multiplier for combined method and temporal decay.
    Returns pd.Series indexed by edge index (int), values in [0,1].
    """
    if weights is None:
        weights = {"is_ntlm": 0.4, "is_network_logon": 0.3, "edge_rarity": 0.3}

    _cfg = config or {}
    scoring_cfg = _cfg.get("scoring", {})
    flow_weights = scoring_cfg.get("flow_weights", {"edge_rarity": 0.4, "is_unusual_dst_port": 0.3, "protocol_rarity": 0.3})
    auth_weight_multiplier = scoring_cfg.get("auth_weight_multiplier", 1.0)

    n = g.ecount()
    if n == 0:
        return pd.Series([], index=pd.Index([], name="edge_index"), dtype=float)

    rarity_rank = edge_features["edge_rarity"].rank(pct=True).values

    mask_valid = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )

    is_auth = np.array([
        g.es[i].attributes().get("type", "flow") == "auth" for i in range(n)
    ])

    w_ntlm = weights.get("is_ntlm", 0.4)
    w_net = weights.get("is_network_logon", 0.3)
    w_rar = weights.get("edge_rarity", 0.3)

    is_ntlm = edge_features["is_ntlm"].values
    is_network = edge_features["is_network_logon"].values

    # Flow edge features (fallback to rarity-only if columns not yet available)
    has_flow_features = (
        "is_unusual_dst_port" in edge_features.columns
        and "protocol_rarity" in edge_features.columns
    )
    if has_flow_features:
        fw_rar = flow_weights.get("edge_rarity", 0.4)
        fw_port = flow_weights.get("is_unusual_dst_port", 0.3)
        fw_proto = flow_weights.get("protocol_rarity", 0.3)
        is_unusual_port = edge_features["is_unusual_dst_port"].values
        protocol_rarity = edge_features["protocol_rarity"].rank(pct=True).values
        flow_score = fw_rar * rarity_rank + fw_port * is_unusual_port + fw_proto * protocol_rarity
    else:
        flow_score = rarity_rank

    raw = np.where(
        is_auth,
        w_ntlm * is_ntlm + w_net * is_network + w_rar * rarity_rank,
        flow_score,
    )

    # Auth weight multiplier (amplifies auth edge signal for combined method)
    if auth_weight_multiplier != 1.0:
        raw = np.where(is_auth, raw * auth_weight_multiplier, raw)

    # Temporal decay (if feature exists)
    if "temporal_decay_weight" in edge_features.columns:
        decay = edge_features["temporal_decay_weight"].values
        raw = raw * decay

    raw = np.where(mask_valid, raw, 0.0)

    return pd.Series(raw, index=pd.Index(range(n), name="edge_index"))


def boost_edges_from_paths(
    edge_scores: pd.Series,
    paths: pd.DataFrame,
    boost_factor: float = 0.1,
) -> pd.Series:
    """Boost edge scores based on path scores — feeds path-level anomaly signal back into edge detection."""
    if paths.empty or boost_factor <= 0:
        return edge_scores

    boosted = edge_scores.copy()
    for _, path_row in paths.iterrows():
        path_edges = path_row.get("path_edges", [])
        path_score = path_row.get("path_score", 0.0)
        if isinstance(path_edges, list):
            for eid in path_edges:
                if eid in boosted.index:
                    boosted.iloc[eid] = min(boosted.iloc[eid] + boost_factor * path_score, 1.0)

    return boosted


def score_paths(
    g: ig.Graph,
    edge_scores: pd.Series,
    max_hops: int = 4,
    top_k: int = 50,
    top_outgoing: int = 10,
    max_workers: int = 12,
) -> pd.DataFrame:
    """BFS path enumeration with anomaly scoring.

    Limits outgoing exploration to top-10 edges by score per node.
    Returns DataFrame sorted by path_score descending, limited to top_k.
    Columns: source_node, path_score, path_nodes, path_edges, path_length.
    """
    total_nodes = g.vcount()
    n_workers = min(os.cpu_count() or 1, max_workers)
    edge_scores_arr = edge_scores.values

    node_names = [g.vs[i]["name"] for i in range(total_nodes)]
    adjacency: dict[int, list[tuple[int, int]]] = {}
    for src in range(total_nodes):
        out_eids = g.incident(src, mode="out")
        if out_eids:
            scored = sorted(out_eids, key=lambda eid: edge_scores_arr[eid], reverse=True)[:top_outgoing]
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
