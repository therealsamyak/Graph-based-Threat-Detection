"""Anomaly scoring for multi-hop paths in igraph graphs.

Scoring is designed to detect lateral movement by flagging:
- Nodes with abnormally high fan-out (redteam lateral movement: fan-out ≈ 6.0 vs benign ≈ 2.5)
- Nodes with anomalous inter-arrival timing (redteam: 214s median vs benign: 6s)
- Edges to new/rare destinations from suspicious sources
- Multi-hop paths connecting compromised hosts through lateral movement
"""

from __future__ import annotations

import logging
import os
from collections import deque
from concurrent.futures import ProcessPoolExecutor
from typing import TYPE_CHECKING

import igraph as ig
import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)

# Redteam lateral movement ports (TCP-only services)
REDTEAM_PORTS = {"445", "139", "22", "3389", "443", "80", "8080"}

def _compute_node_suspiciousness(g: ig.Graph, node_features: pd.DataFrame) -> np.ndarray:
    """Compute per-node suspiciousness score based on lateral movement indicators.
    
    High scores indicate nodes behaving like lateral movement sources:
    - High fan-out ratio (spreading to many destinations)
    - Anomalous inter-arrival timing (slower, more deliberate than normal)
    - High betweenness centrality (acting as bridge/pivot point)
    - High out-degree (initiating many connections)
    
    Returns array of scores in [0, 1] for each node.
    """
    n = g.vcount()
    if n == 0:
        return np.array([])
    
    scores = np.zeros(n, dtype=float)
    
    # --- Fan-out ratio --- 
    # Redteam lateral movement: fan-out ≈ 6.0, benign ≈ 2.5
    # Higher fan-out = more suspicious
    if "fan_out_ratio" in node_features.columns:
        fan_out = node_features["fan_out_ratio"].values.astype(float)
        # Normalize to [0, 1]
        mx = fan_out.max()
        if mx > 0:
            scores += fan_out / mx
    
    # --- Inter-arrival time anomaly ---
    # Redteam: median 214s, benign: 6s → redteam is 35.7x slower
    # Nodes with very high or very low inter-arrival times are suspicious
    if "inter_arrival_mean" in node_features.columns:
        iat = node_features["inter_arrival_mean"].values.astype(float)
        valid = iat > 0
        if valid.any():
            log_iat = np.zeros_like(iat)
            log_iat[valid] = np.log1p(iat[valid])
            mx = log_iat.max()
            if mx > 0:
                scores += log_iat / mx
    
    # --- Betweenness centrality ---
    # Redteam jump box (C17693) has high betweenness — it's a pivot point
    if "betweenness_centrality" in node_features.columns:
        bc = node_features["betweenness_centrality"].values.astype(float)
        mx = bc.max()
        if mx > 0:
            scores += bc / mx
    
    # --- Out-degree ---
    # Redteam sources initiate many connections (reconnaissance + lateral movement)
    if "out_degree" in node_features.columns:
        out_deg = node_features["out_degree"].values.astype(float)
        mx = out_deg.max()
        if mx > 0:
            scores += out_deg / mx
    
    # --- Burst score ---
    # Redteam has different burst patterns
    if "burst_score" in node_features.columns:
        burst = node_features["burst_score"].values.astype(float)
        mx = burst.max()
        if mx > 0:
            scores += burst / mx
    
    # Normalize to [0, 1]
    mx = scores.max()
    if mx > 0:
        scores /= mx
    
    return scores


def _compute_edge_scores_from_features(
    g: ig.Graph,
    node_suspiciousness: np.ndarray,
    edge_features: pd.DataFrame,
) -> np.ndarray:
    """Score each edge based on source/destination suspiciousness and edge properties.
    
    An edge is suspicious when:
    1. Source node is suspicious (high fan-out, anomalous timing)
    2. Destination is a new/rare target for this source
    3. Edge uses a lateral movement port (SMB, SSH, RDP)
    
    Returns array of scores in [0, 1] for each edge.
    """
    n = g.ecount()
    if n == 0:
        return np.array([])
    
    scores = np.zeros(n, dtype=float)
    
    for i in range(n):
        e = g.es[i]
        src_idx = e.source
        dst_idx = e.target
        attrs = e.attributes()
        
        # Component 1: source node suspiciousness (primary signal)
        src_susp = node_suspiciousness[src_idx]
        
        # Component 2: edge rarity (rare connections are more suspicious)
        edge_rarity = float(edge_features.loc[i, "edge_rarity"]) if i in edge_features.index else 0.0
        
        # Component 3: protocol signal (TCP-only for lateral movement)
        protocol = str(attrs.get("protocol", ""))
        protocol_score = 0.1 if protocol == "6" else 0.0  # TCP = 6
        
        # Component 4: port signal (lateral movement ports)
        dst_port = str(attrs.get("dst_port", ""))
        port_score = 0.1 if dst_port in REDTEAM_PORTS else 0.0
        
        # Combined score: source suspiciousness is the main driver
        combined = 0.5 * src_susp + 0.2 * edge_rarity + 0.15 * protocol_score + 0.15 * port_score
        scores[i] = combined
    
    # Min-max scale to [0, 1]
    if len(scores) > 0:
        mn, mx = scores.min(), scores.max()
        if mx - mn > 1e-12:
            scores = (scores - mn) / (mx - mn)
    
    return scores


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


def score_edges(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    node_features: pd.DataFrame | None = None,
    weights: dict[str, float] | None = None,
) -> pd.Series:
    """Score edges for lateral movement detection.
    
    Uses node-level suspiciousness (fan-out, timing, centrality) combined with
    edge-level features (rarity, protocol, port) to produce per-edge scores.
    
    Returns pd.Series indexed by edge index (int), values in [0,1].
    """
    n = g.ecount()
    if n == 0:
        return pd.Series([], dtype=float, name="score")
    
    # Compute node suspiciousness
    node_susp = _compute_node_suspiciousness(g, node_features if node_features is not None else pd.DataFrame())
    
    # Score edges based on node suspiciousness + edge properties
    edge_scores_arr = _compute_edge_scores_from_features(g, node_susp, edge_features)
    
    return pd.Series(edge_scores_arr, index=pd.Index(range(n), name="edge_index"), name="score")


def compute_auc(
    g: ig.Graph,
    edge_scores: pd.Series,
    red_pairs: set[tuple[str, str]],
) -> float:
    """Compute ROC-AUC for edge-level detection.
    
    Labels edges as positive if (src, dst) is a redteam pair, negative otherwise.
    Returns AUC score (0.5 = random, 1.0 = perfect).
    """
    if g.ecount() == 0 or len(red_pairs) == 0:
        return 0.0
    
    labels = []
    scores = []
    for i in range(g.ecount()):
        e = g.es[i]
        pair = (g.vs[e.source]["name"], g.vs[e.target]["name"])
        labels.append(1.0 if pair in red_pairs else 0.0)
        if i in edge_scores.index:
            scores.append(float(edge_scores.loc[i]))
        else:
            scores.append(0.0)
    
    labels_arr = np.array(labels)
    scores_arr = np.array(scores)
    
    # Need both positive and negative samples
    if labels_arr.sum() == 0 or labels_arr.sum() == len(labels_arr):
        return 0.0
    
    try:
        auc = roc_auc_score(labels_arr, scores_arr)
        return round(auc, 4)
    except Exception:
        return 0.0


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
        edge_scores = score_edges(g, edge_features, all_features.get("node_features"))

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


def compute_feature_importance(
    g: ig.Graph,
    node_features: pd.DataFrame,
    edge_features: pd.DataFrame,
    edge_scores: pd.Series,
    red_pairs: set[tuple[str, str]],
) -> dict:
    """Analyze which features contribute most to detection.
    
    For each feature, computes the correlation between feature values and edge scores,
    separately for redteam and baseline edges.
    
    Returns dict with feature importance analysis.
    """
    result: dict = {
        "node_feature_importance": {},
        "edge_feature_importance": {},
        "redteam_vs_baseline_stats": {},
    }
    
    # --- Node feature importance ---
    # For each node feature, compare mean values for redteam vs baseline nodes
    redteam_nodes: set[str] = set()
    for pair in red_pairs:
        redteam_nodes.add(pair[0])
        redteam_nodes.add(pair[1])
    
    for col in node_features.columns:
        vals = node_features[col].values.astype(float)
        node_names = node_features.index.tolist()
        
        red_vals = []
        base_vals = []
        for i, name in enumerate(node_names):
            if name in redteam_nodes:
                red_vals.append(vals[i])
            else:
                base_vals.append(vals[i])
        
        if red_vals and base_vals:
            red_mean = float(np.mean(red_vals))
            base_mean = float(np.mean(base_vals))
            ratio = red_mean / base_mean if base_mean > 0 else float("inf")
            result["node_feature_importance"][col] = {
                "redteam_mean": round(red_mean, 4),
                "baseline_mean": round(base_mean, 4),
                "ratio": round(ratio, 4) if ratio != float("inf") else "inf",
            }
    
    # --- Edge feature importance ---
    # Correlation between each edge feature and the edge score
    for col in edge_features.columns:
        vals = edge_features[col].values.astype(float)
        scores = edge_scores.values
        corr = float(np.corrcoef(vals, scores)[0, 1]) if len(vals) > 1 else 0.0
        result["edge_feature_importance"][col] = {
            "score_correlation": round(corr, 4),
        }
    
    # --- Redteam vs baseline edge statistics ---
    red_scores = []
    base_scores = []
    for i in range(g.ecount()):
        e = g.es[i]
        pair = (g.vs[e.source]["name"], g.vs[e.target]["name"])
        score = float(edge_scores.loc[i]) if i in edge_scores.index else 0.0
        if pair in red_pairs:
            red_scores.append(score)
        else:
            base_scores.append(score)
    
    if red_scores and base_scores:
        result["redteam_vs_baseline_stats"] = {
            "redteam_mean_score": round(float(np.mean(red_scores)), 4),
            "baseline_mean_score": round(float(np.mean(base_scores)), 4),
            "redteam_std_score": round(float(np.std(red_scores)), 4),
            "baseline_std_score": round(float(np.std(base_scores)), 4),
            "redteam_max_score": round(float(np.max(red_scores)), 4),
            "baseline_max_score": round(float(np.max(base_scores)), 4),
            "redteam_count": len(red_scores),
            "baseline_count": len(base_scores),
        }
    
    return result
