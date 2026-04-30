"""Single-source baselines: flow-only, auth-only, and combined methods."""

from __future__ import annotations

import time

import numpy as np
import pandas as pd

from src.features import extract_all_features
from src.graph_builder import build_auth_graph, build_combined_graph, build_flow_graph
from src.scorer import score_edges, score_graph, score_paths


def _run_method(
    method_name: str,
    g,
    redteam_df: pd.DataFrame,
) -> dict:
    """Shared pipeline: features → score → simple detection metrics."""
    t0 = time.perf_counter()
    all_features = extract_all_features(g)
    edge_scores = score_edges(g, all_features["edge_features"])
    score_graph(g, all_features, edge_scores)
    paths = score_paths(g, edge_scores)
    _elapsed = time.perf_counter() - t0  # noqa: F841 – kept for future latency reporting

    if not redteam_df.empty:
        threshold = 0.5
        edge_vals = edge_scores.values
        if len(edge_vals) > 0:
            threshold = float(np.percentile(edge_vals, 95))
    else:
        threshold = 0.5

    red_pairs = (
        set(zip(redteam_df["src_comp"].astype(str), redteam_df["dst_comp"].astype(str)))
        if not redteam_df.empty
        else set()
    )
    n_red = len(red_pairs) if red_pairs else 1

    # Count red-team edges in the graph for FPR calculation
    n_edges = g.ecount()
    red_edge_count = 0
    for i in range(n_edges):
        src_name = g.es[i].source_vertex["name"]
        dst_name = g.es[i].target_vertex["name"]
        if (src_name, dst_name) in red_pairs:
            red_edge_count += 1

    # Detection: count red-team (src,dst) pairs that appear in anomalous paths
    anomalous_paths = paths[paths["path_score"] > threshold] if len(paths) > 0 else pd.DataFrame()
    detected_pairs: set[tuple[str, str]] = set()
    if len(anomalous_paths) > 0:
        for _, row in anomalous_paths.iterrows():
            nodes = row["path_nodes"]
            for i in range(len(nodes) - 1):
                pair = (nodes[i], nodes[i + 1])
                if pair in red_pairs:
                    detected_pairs.add(pair)

    detected = len(detected_pairs)
    recall = min(detected / n_red, 1.0) if n_red > 0 else 0.0

    anomalous_edge_count = int((edge_scores > threshold).sum())
    normal_edges = max(n_edges - red_edge_count, 1)
    flagged_normal = max(anomalous_edge_count - red_edge_count, 0)
    fpr = flagged_normal / normal_edges

    # Precision: detected red-team pairs / total anomalous edges
    precision = detected / max(anomalous_edge_count, 1)
    if recall + precision > 0:
        f1 = 2 * recall * precision / (recall + precision)
    else:
        f1 = 0.0

    return {
        "method_name": method_name,
        "recall": float(recall),
        "fpr": float(fpr),
        "f1": float(f1),
        "latency": 0.0,
        "throughput": 0.0,
    }


def run_flow_only_baseline(
    auth_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    redteam_df: pd.DataFrame,
    window_seconds: int = 3600,
) -> dict:
    """Baseline using flow graph only."""
    g = build_flow_graph(flow_df)
    return _run_method("flow_only", g, redteam_df)


def run_auth_only_baseline(
    auth_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    redteam_df: pd.DataFrame,
    window_seconds: int = 3600,
) -> dict:
    """Baseline using auth graph only."""
    g = build_auth_graph(auth_df)
    return _run_method("auth_only", g, redteam_df)


def run_combined_method(
    auth_df: pd.DataFrame,
    flow_df: pd.DataFrame,
    redteam_df: pd.DataFrame,
    window_seconds: int = 3600,
) -> dict:
    """Combined method using both auth and flow graphs."""
    g = build_combined_graph(auth_df, flow_df)
    return _run_method("combined", g, redteam_df)
