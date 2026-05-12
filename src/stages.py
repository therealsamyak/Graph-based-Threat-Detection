"""Pipeline stage functions: load, build, score, detect."""

from __future__ import annotations

import logging
import time
from collections import namedtuple
from pathlib import Path

import pandas as pd

from src.data.lanl import (
    AUTH_COLUMNS,
    AUTH_NUMERIC,
    FLOW_COLUMNS,
    FLOW_NUMERIC,
    build_window_intervals,
    load_redteam,
)
from src.detection import compute_pair_metrics, optimize_threshold
from src.features import extract_all_features
from src.graph.builder import StreamingGraphBuilder, stream_gz_to_graph
from src.scoring.edges import boost_edges_from_paths, score_edges
from src.scoring.paths import score_graph, score_paths
from src.types import DetectionParams, PipelineConfig
from src.utils import compute_edge_pair_names

logger = logging.getLogger(__name__)

MethodResult = namedtuple(
    "MethodResult",
    [
        "method_name",
        "graph",
        "edge_scores",
        "paths",
        "threshold",
        "edge_features",
        "node_features",
        "graph_features",
        "metrics",
        "graph_result",
        "build_time",
        "score_time",
        "total_events",
        "graph_edges",
        "edge_pair_names",
        "rt_in_graph",
        "result_dict",
    ],
)


def load_redteam_data(
    data_dir: str,
    window_seconds: int,
) -> tuple[pd.DataFrame, set, list]:
    rt = load_redteam(str(Path(data_dir) / "redteam.txt.gz"))
    red_pairs = set(zip(rt["src_comp"].astype(str), rt["dst_comp"].astype(str)))
    windows = build_window_intervals(rt, window_seconds)
    logger.info(f"Red team: {len(rt)} events, {len(windows)} merged windows")
    return rt, red_pairs, windows


def run_method_pipeline(
    method_name: str,
    data_dir: str,
    windows: list,
    red_pairs: set,
    config: PipelineConfig,
    max_events: int | None = None,
    feed_auth: bool | None = True,
    feed_flow: bool | None = True,
) -> MethodResult:
    scoring = config.scoring
    data_path = Path(data_dir)

    logger.info(f"Streaming + building: {method_name}")
    t0 = time.perf_counter()

    graph = StreamingGraphBuilder()

    n_auth = 0
    if feed_auth:
        n_auth = stream_gz_to_graph(
            str(data_path / "auth.txt.gz"),
            AUTH_COLUMNS, windows, AUTH_NUMERIC,
            graph, graph.feed_auth_event,
            progress_every=config.graph.progress_every,
            max_events=max_events,
        )

    n_flow = 0
    if feed_flow:
        n_flow = stream_gz_to_graph(
            str(data_path / "flows.txt.gz"),
            FLOW_COLUMNS, windows, FLOW_NUMERIC,
            graph, graph.feed_flow_event,
            progress_every=config.graph.progress_every,
            max_events=max_events,
        )

    g = graph.build()
    build_time = time.perf_counter() - t0
    logger.info(f"  Streamed {n_auth:,} auth + {n_flow:,} flow in {build_time:.1f}s")
    logger.info(f"  Graph: {g.vcount():,} nodes, {g.ecount():,} edges")

    del graph

    edge_pair_names = compute_edge_pair_names(g)
    graph_edges = set(edge_pair_names)
    rt_in_graph = red_pairs & graph_edges
    logger.info(f"  Red team pairs in graph: {len(rt_in_graph)}/{len(red_pairs)}")

    t1 = time.perf_counter()
    logger.info(f"  Extracting features ({g.vcount():,} nodes, {g.ecount():,} edges)...")
    all_feat = extract_all_features(g, config=config.to_dict())
    logger.info(f"  Features extracted in {time.perf_counter() - t1:.1f}s, scoring edges...")

    weights_dict = scoring.weights.to_dict()
    edge_scores = score_edges(g, all_feat["edge_features"], weights=weights_dict, config=config.to_dict())
    logger.info("  Edge scores computed, enumerating paths (this may take a while)...")

    paths = score_paths(
        g, edge_scores,
        max_hops=scoring.max_hops,
        top_k=scoring.top_k_paths,
        top_outgoing=scoring.top_outgoing_per_node,
        max_workers=config.features.max_workers,
    )
    logger.info(f"  Scored {len(paths):,} paths, computing graph-level scores...")

    edge_scores = boost_edges_from_paths(edge_scores, paths, boost_factor=scoring.path_boost_factor)
    logger.info(f"  Applied path boost (factor={scoring.path_boost_factor})")

    graph_result = score_graph(g, all_feat, edge_scores, paths=paths)
    score_time = time.perf_counter() - t1
    logger.info(f"  Scoring completed in {score_time:.1f}s")

    ef = all_feat["edge_features"]
    mask_valid = (
        (ef["is_self_loop"].values == 0.0)
        & (ef["is_user_edge"].values == 0.0)
    )

    params = DetectionParams(
        edge_scores=edge_scores,
        mask_valid=mask_valid,
        edge_pair_names=tuple(edge_pair_names),
        positive_pairs_in_graph=frozenset(rt_in_graph),
        all_positive_pairs=frozenset(red_pairs),
        all_graph_edges=frozenset(graph_edges),
    )

    threshold, best_pct = optimize_threshold(
        params,
        threshold_mode=scoring.threshold_mode,
        search_range=scoring.threshold_search_range,
        default_percentile=scoring.threshold_percentile,
    )

    metrics = compute_pair_metrics(params, threshold)

    total_events = n_auth + n_flow
    result_dict = {
        "method": method_name,
        "dataset": "LANL-2015",
        "recall": round(metrics["recall"], 4),
        "fpr": round(metrics["fpr"], 4),
        "f1": round(metrics["f1"], 4),
        "auc": round(metrics["auc"], 4),
        "latency": round(build_time + score_time, 2),
        "throughput": round(total_events / (build_time + score_time), 1),
        "graph_nodes": g.vcount(),
        "graph_edges": g.ecount(),
        "rt_pairs_in_graph": len(rt_in_graph),
        "anomalous_pairs": len(metrics["anomalous_pairs"]),
        "threshold": round(threshold, 4),
        "threshold_mode": scoring.threshold_mode,
        "threshold_percentile_used": best_pct if scoring.threshold_mode == "auto_optimize" else scoring.threshold_percentile,
        "max_path_score": round(graph_result["max_path_score"], 4),
        "mean_edge_score": round(graph_result["mean_edge_score"], 4),
    }
    logger.info(
        f"  {method_name}: recall={metrics['recall']:.4f}, fpr={metrics['fpr']:.4f}, f1={metrics['f1']:.4f}"
    )

    return MethodResult(
        method_name=method_name,
        graph=g,
        edge_scores=edge_scores,
        paths=paths,
        threshold=threshold,
        edge_features=ef,
        node_features=all_feat["node_features"],
        graph_features=all_feat["graph_features"],
        metrics=metrics,
        graph_result=graph_result,
        build_time=build_time,
        score_time=score_time,
        total_events=total_events,
        graph_edges=graph_edges,
        edge_pair_names=edge_pair_names,
        rt_in_graph=rt_in_graph,
        result_dict=result_dict,
    )
