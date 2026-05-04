"""DAPT2020 graph-based detection: construct igraph from flow records, apply graph scoring pipeline."""

from __future__ import annotations

import logging
import time

import igraph as ig

from src.data.dapt import load_dapt2020
from src.detection import compute_pair_metrics, optimize_threshold
from src.features.graph import extract_all_features
from src.scoring.edges import boost_edges_from_paths, score_edges
from src.scoring.paths import score_graph, score_paths

logger = logging.getLogger(__name__)

FLOW_AGG_COLUMNS = [
    "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
    "Total Length of Fwd Packet", "Total Length of Bwd Packet",
    "Flow Bytes/s", "Flow Packets/s",
    "Fwd Packet Length Mean", "Bwd Packet Length Mean",
    "Fwd Packets/s", "Bwd Packets/s",
    "Flow IAT Mean", "Packet Length Mean",
]


def run_dapt_graph(
    data_dir: str = "data/DAPT2020",
    max_rows: int | None = None,
    config: dict | None = None,
) -> dict:
    _cfg = config or {}
    scoring_cfg = _cfg.get("scoring", {})
    feat_cfg = _cfg.get("features", {})
    weights = scoring_cfg.get("weights", {"is_ntlm": 0.4, "is_network_logon": 0.3, "edge_rarity": 0.3})
    max_hops = scoring_cfg.get("max_hops", 4)
    top_k_paths = scoring_cfg.get("top_k_paths", 50)
    top_outgoing = scoring_cfg.get("top_outgoing_per_node", 10)
    max_workers = feat_cfg.get("max_workers", 12)
    path_boost_factor = scoring_cfg.get("path_boost_factor", 0.1)
    threshold_mode = scoring_cfg.get("threshold_mode", "auto_optimize")
    threshold_percentile = scoring_cfg.get("threshold_percentile", 90)
    threshold_search_range = scoring_cfg.get("threshold_search_range", [90, 95, 97, 99, 99.5, 99.9])

    t0 = time.perf_counter()
    df = load_dapt2020(data_dir)
    if max_rows is not None:
        df = df.head(max_rows)
    load_time = time.perf_counter() - t0
    logger.info(f"DAPT graph: loaded {len(df)} rows in {load_time:.1f}s")

    agg_cols_available = [c for c in FLOW_AGG_COLUMNS if c in df.columns]
    group_cols = ["Src IP", "Dst IP"]

    agg_dict: dict = {"is_lateral_movement": "max"}
    for c in agg_cols_available:
        agg_dict[c] = "mean"

    if "Protocol" in df.columns:
        agg_dict["Protocol"] = "first"

    grouped = df.groupby(group_cols, as_index=False).agg(agg_dict)
    logger.info(f"DAPT graph: {len(grouped)} unique src-dst pairs")

    g = ig.Graph(directed=True)
    node_set: set[str] = set()

    for _, row in grouped.iterrows():
        src = str(row["Src IP"])
        dst = str(row["Dst IP"])
        if src not in node_set:
            g.add_vertex(src, node_type="computer", is_machine=True)
            node_set.add(src)
        if dst not in node_set:
            g.add_vertex(dst, node_type="computer", is_machine=True)
            node_set.add(dst)

        edge_attrs = {"type": "flow", "weight": 1}
        for c in agg_cols_available:
            val = row.get(c)
            if val is not None:
                try:
                    edge_attrs[c] = float(val)
                except (ValueError, TypeError):
                    pass
        if "Protocol" in row.index:
            edge_attrs["protocol"] = str(row["Protocol"])
        g.add_edge(src, dst, **edge_attrs)

    logger.info(f"DAPT graph: {g.vcount():,} nodes, {g.ecount():,} edges")

    edge_pair_names = [
        (g.vs[g.es[i].source]["name"], g.vs[g.es[i].target]["name"])
        for i in range(g.ecount())
    ]

    gt_map = {}
    for _, row in grouped.iterrows():
        pair = (str(row["Src IP"]), str(row["Dst IP"]))
        if pair not in gt_map:
            gt_map[pair] = int(row.get("is_lateral_movement", 0))

    lateral_pairs = {pair for pair, lbl in gt_map.items() if lbl == 1}
    graph_edges = set(edge_pair_names)
    lm_in_graph = lateral_pairs & graph_edges
    logger.info(f"DAPT graph: {len(lateral_pairs)} lateral pairs, {len(lm_in_graph)} in graph")

    t1 = time.perf_counter()
    all_feat = extract_all_features(g, config=_cfg)
    logger.info(f"DAPT graph: features extracted in {time.perf_counter() - t1:.1f}s")

    edge_scores = score_edges(g, all_feat["edge_features"], weights=weights, config=_cfg)
    logger.info("DAPT graph: edge scores computed, enumerating paths...")

    paths = score_paths(g, edge_scores, max_hops=max_hops, top_k=top_k_paths,
                        top_outgoing=top_outgoing, max_workers=max_workers)
    logger.info(f"DAPT graph: {len(paths):,} paths scored")

    edge_scores = boost_edges_from_paths(edge_scores, paths, boost_factor=path_boost_factor)
    graph_result = score_graph(g, all_feat, edge_scores, paths=paths)

    ef = all_feat["edge_features"]
    mask_valid = (
        (ef["is_self_loop"].values == 0.0)
        & (ef["is_user_edge"].values == 0.0)
    )

    threshold, best_pct = optimize_threshold(
        edge_scores, mask_valid, edge_pair_names,
        lm_in_graph, lateral_pairs,
        threshold_mode=threshold_mode,
        search_range=threshold_search_range,
        default_percentile=threshold_percentile,
    )

    metrics = compute_pair_metrics(
        edge_scores, mask_valid, edge_pair_names,
        graph_edges, lm_in_graph, lateral_pairs,
        threshold,
    )

    total_time = time.perf_counter() - t0
    return {
        "method": "graph_combined",
        "dataset": "DAPT2020",
        "recall": round(metrics["recall"], 4),
        "fpr": round(metrics["fpr"], 4),
        "f1": round(metrics["f1"], 4),
        "auc": round(metrics["auc"], 4),
        "latency": round(total_time, 2),
        "throughput": round(len(df) / max(total_time, 1e-10), 1),
        "graph_nodes": g.vcount(),
        "graph_edges": g.ecount(),
        "rt_pairs_in_graph": len(lm_in_graph),
        "anomalous_pairs": len(metrics["anomalous_pairs"]),
        "threshold": round(threshold, 4),
        "threshold_mode": threshold_mode,
        "threshold_percentile_used": best_pct if threshold_mode == "auto_optimize" else threshold_percentile,
        "max_path_score": round(graph_result["max_path_score"], 4),
        "mean_edge_score": round(graph_result["mean_edge_score"], 4),
    }
