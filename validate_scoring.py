"""Validate scoring fixes against existing experiment data.

Proves the scoring pipeline works correctly on the 20260502_024853 combined
experiment WITHOUT re-running the 3h streaming pipeline.

Usage: uv run python validate_scoring.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import igraph as ig
import numpy as np
import pandas as pd

from src.features import extract_edge_features
from src.scorer import score_edges

RESULTS_DIR = Path("results/20260502_024853")
EDGES_CSV = RESULTS_DIR / "combined" / "graph_edges.csv"
RT_JSON = RESULTS_DIR / "redteam" / "redteam_pairs.json"


def load_redteam_pairs() -> set[tuple[str, str]]:
    with open(RT_JSON) as f:
        data = json.load(f)
    return {(p["src"], p["dst"]) for p in data}


def build_graph_from_csv(csv_path: str) -> ig.Graph:
    print(f"Loading edges from {csv_path}...")
    t0 = time.perf_counter()
    df = pd.read_csv(csv_path, dtype=str)
    print(f"  Loaded {len(df):,} rows in {time.perf_counter() - t0:.1f}s")

    all_names = set(df["src"].tolist() + df["dst"].tolist())
    print(f"  Unique nodes: {len(all_names):,}")

    name_to_idx = {name: i for i, name in enumerate(sorted(all_names))}

    n_edges = len(df)
    sources = [name_to_idx[n] for n in df["src"]]
    targets = [name_to_idx[n] for n in df["dst"]]

    edge_attrs: dict[str, list] = {
        "type": df["type"].fillna("").tolist(),
        "auth_type": df["auth_type"].fillna("").tolist(),
        "logon_type": df["logon_type"].fillna("").tolist(),
        "auth_orientation": df["auth_orientation"].fillna("").tolist(),
        "success": df["success"].fillna("").tolist(),
        "time": pd.to_numeric(df["time"], errors="coerce").fillna(0.0).tolist(),
        "weight": pd.to_numeric(df["weight"], errors="coerce").fillna(1).astype(int).tolist(),
        "first_time": pd.to_numeric(df["first_time"], errors="coerce").fillna(0.0).tolist(),
        "last_time": pd.to_numeric(df["last_time"], errors="coerce").fillna(0.0).tolist(),
        "protocol": df["protocol"].fillna("").tolist(),
        "src_port": pd.to_numeric(df["src_port"], errors="coerce").fillna(0).astype(int).tolist(),
        "dst_port": pd.to_numeric(df["dst_port"], errors="coerce").fillna(0).astype(int).tolist(),
        "pkt_count": pd.to_numeric(df["pkt_count"], errors="coerce").fillna(0).astype(int).tolist(),
        "byte_count": pd.to_numeric(df["byte_count"], errors="coerce").fillna(0).astype(int).tolist(),
        "duration": pd.to_numeric(df["duration"], errors="coerce").fillna(0.0).tolist(),
    }

    print(f"Building igraph ({len(all_names):,} vertices, {n_edges:,} edges)...")
    t0 = time.perf_counter()
    g = ig.Graph(directed=True)
    g.add_vertices(len(all_names), attributes={"name": sorted(all_names)})
    g.add_edges(list(zip(sources, targets)), attributes=edge_attrs)
    print(f"  Graph built in {time.perf_counter() - t0:.1f}s")
    print(f"  Graph: {g.vcount():,} nodes, {g.ecount():,} edges")
    return g


def compute_detection_metrics(
    g: ig.Graph,
    edge_scores: pd.Series,
    ef: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
) -> dict:
    graph_edges: set[tuple[str, str]] = set()
    for e in g.es:
        graph_edges.add((g.vs[e.source]["name"], g.vs[e.target]["name"]))
    rt_in_graph = red_pairs & graph_edges

    mask_valid = (
        (ef["is_self_loop"].values == 0.0)
        & (ef["is_user_edge"].values == 0.0)
    )
    scoring_scores = edge_scores[mask_valid]
    threshold = float(np.percentile(scoring_scores.values, 90)) if len(scoring_scores) > 0 else 0.5
    if len(scoring_scores) > 0 and scoring_scores.std() < 1e-10:
        threshold = float(scoring_scores.max()) + 0.01

    anomalous_mask = mask_valid & (edge_scores > threshold)
    anomalous_pairs: set[tuple[str, str]] = set()
    for idx in edge_scores.index[anomalous_mask]:
        anomalous_pairs.add((g.vs[g.es[idx].source]["name"], g.vs[g.es[idx].target]["name"]))

    detected_pairs = anomalous_pairs & rt_in_graph
    recall = len(detected_pairs) / len(red_pairs) if red_pairs else 0.0
    true_negatives = len(graph_edges - anomalous_pairs - rt_in_graph)
    false_positives = len(anomalous_pairs - rt_in_graph)
    fpr = false_positives / max(false_positives + true_negatives, 1)
    precision = len(detected_pairs) / max(len(anomalous_pairs), 1)
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

    return {
        "red_pairs": red_pairs,
        "rt_in_graph": rt_in_graph,
        "graph_edges": graph_edges,
        "anomalous_pairs": anomalous_pairs,
        "detected_pairs": detected_pairs,
        "threshold": threshold,
        "recall": recall,
        "precision": precision,
        "fpr": fpr,
        "f1": f1,
        "mask_valid": mask_valid,
    }


def main():
    print("=" * 60)
    print("Scoring Validation — Edge-Level Detection")
    print("=" * 60)

    red_pairs = load_redteam_pairs()
    print(f"\nRed team pairs: {len(red_pairs)}")

    g = build_graph_from_csv(str(EDGES_CSV))

    print("\nExtracting edge features...")
    t0 = time.perf_counter()
    ef = extract_edge_features(g)
    print(f"  Features extracted in {time.perf_counter() - t0:.1f}s")
    print(f"  Feature columns: {list(ef.columns)}")

    print("\nScoring edges...")
    t0 = time.perf_counter()
    edge_scores = score_edges(g, ef)
    print(f"  Edge scores computed in {time.perf_counter() - t0:.1f}s")
    print(f"  Score range: [{edge_scores.min():.4f}, {edge_scores.max():.4f}]")
    print(f"  Score mean: {edge_scores.mean():.4f}, std: {edge_scores.std():.4f}")

    print("\nComputing detection metrics...")
    metrics = compute_detection_metrics(g, edge_scores, ef, red_pairs)

    rt_in_graph = metrics["rt_in_graph"]
    graph_edges = metrics["graph_edges"]
    non_rt_edges = graph_edges - rt_in_graph

    rt_scores = []
    non_rt_scores = []
    for i in range(g.ecount()):
        src_name = g.vs[g.es[i].source]["name"]
        dst_name = g.vs[g.es[i].target]["name"]
        pair = (src_name, dst_name)
        if pair in rt_in_graph:
            rt_scores.append(edge_scores.iloc[i])
        elif pair in non_rt_edges:
            non_rt_scores.append(edge_scores.iloc[i])

    rt_mean_score = float(np.mean(rt_scores)) if rt_scores else 0.0
    non_rt_mean_score = float(np.mean(non_rt_scores)) if non_rt_scores else 0.0
    edge_score_std = float(edge_scores.std())

    print("\n" + "=" * 60)
    print("DETECTION RESULTS")
    print("=" * 60)
    print(f"  Red team pairs total:       {len(red_pairs)}")
    print(f"  Red team pairs in graph:    {len(rt_in_graph)}")
    print(f"  Anomalous pairs detected:   {len(metrics['anomalous_pairs'])}")
    print(f"  True positives (detected):  {len(metrics['detected_pairs'])}")
    print(f"  Threshold (p90):            {metrics['threshold']:.4f}")
    print(f"\n  Recall:    {metrics['recall']:.4f}")
    print(f"  Precision: {metrics['precision']:.4f}")
    print(f"  FPR:       {metrics['fpr']:.4f}")
    print(f"  F1:        {metrics['f1']:.4f}")
    print(f"\n  RT edge mean score:      {rt_mean_score:.4f}")
    print(f"  Non-RT edge mean score:  {non_rt_mean_score:.4f}")
    print(f"  RT vs non-RT gap:        {rt_mean_score - non_rt_mean_score:.4f}")
    print(f"  Edge score std:          {edge_score_std:.6f}")

    print("\n" + "=" * 60)
    print("ASSERTIONS")
    print("=" * 60)

    assert metrics["recall"] > 0.5, f"recall={metrics['recall']} < 0.5"
    print(f"  ✓ Recall > 0.5: {metrics['recall']:.4f}")

    assert rt_mean_score > non_rt_mean_score + 0.2, (
        f"RT mean {rt_mean_score:.4f} not sufficiently above non-RT {non_rt_mean_score:.4f}"
    )
    print(f"  ✓ RT mean ({rt_mean_score:.4f}) > non-RT mean ({non_rt_mean_score:.4f}) + 0.2")

    assert edge_score_std > 0.01, f"edge score std {edge_score_std:.6f} too low"
    print(f"  ✓ Edge score std > 0.01: {edge_score_std:.6f}")

    print("\n✅ All assertions passed!")


if __name__ == "__main__":
    main()
