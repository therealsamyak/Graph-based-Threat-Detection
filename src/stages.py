"""Pipeline stage functions: load, build, score, detect."""

from __future__ import annotations

import logging
import time
from collections import namedtuple
from pathlib import Path

import numpy as np
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
from src.optimization import WeightOptimizer
from src.scoring.edges import boost_edges_from_paths, score_edges
from src.scoring.paths import score_graph, score_paths
from src.types import DetectionParams, PipelineConfig
from src.utils import compute_edge_pair_names
from src.variants import get_variant

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


def _resolve_data_file(data_dir: str, base_name: str) -> str:
    """Return the path to a data file, preferring .gz if it exists, falling back to .txt."""
    gz_path = Path(data_dir) / f"{base_name}.gz"
    if gz_path.exists():
        return str(gz_path)
    txt_path = Path(data_dir) / base_name
    if txt_path.exists():
        return str(txt_path)
    return str(gz_path)  # default to .gz for error message


def load_redteam_data(
    data_dir: str,
    window_seconds: int,
) -> tuple[pd.DataFrame, set, list]:
    rt = load_redteam(_resolve_data_file(data_dir, "redteam.txt"))
    red_pairs = set(zip(rt["src_comp"].astype(str), rt["dst_comp"].astype(str)))
    windows = build_window_intervals(rt, window_seconds)
    logger.info(f"Red team: {len(rt)} events, {len(windows)} merged windows")
    return rt, red_pairs, windows


def _score_detect_graph(
    *,
    method_name: str,
    dataset: str,
    g,
    red_pairs: set,
    build_time: float,
    total_events: int,
    config: PipelineConfig,
    output_dir: str | None = None,
) -> MethodResult:
    descriptor = get_variant(method_name)
    feature_whitelist = list(descriptor.feature_whitelist)

    scoring = config.scoring
    edge_pair_names = compute_edge_pair_names(g)
    graph_edges = set(edge_pair_names)
    rt_in_graph = red_pairs & graph_edges
    logger.info(f"  Red team pairs in graph: {len(rt_in_graph)}/{len(red_pairs)}")

    t1 = time.perf_counter()
    logger.info(
        f"  Extracting features ({g.vcount():,} nodes, {g.ecount():,} edges)..."
    )
    all_feat = extract_all_features(g, config=config.to_dict(), variant_name=method_name)
    logger.info(
        f"  Features extracted in {time.perf_counter() - t1:.1f}s, scoring edges..."
    )

    ef = all_feat["edge_features"]
    mask_valid = (ef["is_self_loop"].values == 0.0) & (ef["is_user_edge"].values == 0.0)
    labels = np.array([1.0 if pair in red_pairs else 0.0 for pair in edge_pair_names])

    available_features = set(ef.columns)
    missing_features = [feat for feat in feature_whitelist if feat not in available_features]
    if missing_features:
        raise ValueError(
            f"Variant '{method_name}': Missing features: {missing_features}. "
            f"Available: {sorted(available_features)}"
        )

    logger.info(f"  Variant '{method_name}': {len(feature_whitelist)} features")

    logger.info("  Running weight optimization...")
    opt = WeightOptimizer(
        ef[mask_valid].reset_index(drop=True),
        labels[mask_valid],
        feature_whitelist,
    )
    opt_output_dir = str(Path(output_dir) / "optimization") if output_dir else None
    opt_result = opt.optimize(output_dir=opt_output_dir)
    weights_dict = {k: v for k, v in opt_result.items() if k in feature_whitelist}
    logger.info(f"  Optimized weights: {weights_dict}")
    logger.info(f"  Optimized AUC: {opt_result['auc']:.4f}")

    edge_scores = score_edges(g, ef, weights=weights_dict, config=config.to_dict())
    logger.info("  Edge scores computed, enumerating paths (this may take a while)...")

    paths = score_paths(
        g,
        edge_scores,
        max_hops=scoring.max_hops,
        top_k=scoring.top_k_paths,
        top_outgoing=scoring.top_outgoing_per_node,
        max_workers=config.features.max_workers,
        variant_name=method_name,
    )
    logger.info(f"  Scored {len(paths):,} paths, computing graph-level scores...")

    edge_scores = boost_edges_from_paths(
        edge_scores, paths, boost_factor=scoring.path_boost_factor
    )
    logger.info(f"  Applied path boost (factor={scoring.path_boost_factor})")

    graph_result = score_graph(g, all_feat, edge_scores, paths=paths)
    score_time = time.perf_counter() - t1
    logger.info(f"  Scoring completed in {score_time:.1f}s")

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

    elapsed = build_time + score_time
    result_dict = {
        "method": method_name,
        "dataset": dataset,
        "recall": round(metrics["recall"], 4),
        "fpr": round(metrics["fpr"], 4),
        "f1": round(metrics["f1"], 4),
        "auc": round(metrics["auc"], 4),
        "latency": round(elapsed, 2),
        "throughput": round(total_events / elapsed, 1) if elapsed > 0 else 0.0,
        "graph_nodes": g.vcount(),
        "graph_edges": g.ecount(),
        "rt_pairs_in_graph": len(rt_in_graph),
        "anomalous_pairs": len(metrics["anomalous_pairs"]),
        "threshold": round(threshold, 4),
        "threshold_mode": scoring.threshold_mode,
        "threshold_percentile_used": best_pct
        if scoring.threshold_mode == "auto_optimize"
        else scoring.threshold_percentile,
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


def run_method_pipeline(
    data_dir: str,
    windows: list,
    red_pairs: set,
    config: PipelineConfig,
    max_events: int | None = None,
    output_dir: str | None = None,
    variant: str = "combined",
) -> MethodResult:
    data_path = Path(data_dir)
    descriptor = get_variant(variant)
    method_name = descriptor.name
    event_filter = descriptor.event_filter
    logger.info(f"Streaming + building: {method_name} (event_filter={event_filter})")
    t0 = time.perf_counter()

    graph = StreamingGraphBuilder()
    n_auth = 0
    n_flow = 0

    if event_filter in ("both", "auth"):
        n_auth = stream_gz_to_graph(
            _resolve_data_file(str(data_path), "auth.txt"),
            AUTH_COLUMNS,
            windows,
            AUTH_NUMERIC,
            graph,
            graph.feed_auth_event,
            progress_every=config.graph.progress_every,
            max_events=max_events,
        )

    if event_filter in ("both", "flow"):
        n_flow = stream_gz_to_graph(
            _resolve_data_file(str(data_path), "flows.txt"),
            FLOW_COLUMNS,
            windows,
            FLOW_NUMERIC,
            graph,
            graph.feed_flow_event,
            progress_every=config.graph.progress_every,
            max_events=max_events,
        )

    g = graph.build()
    build_time = time.perf_counter() - t0
    logger.info(
        f"  Streamed {n_auth:,} auth + {n_flow:,} flow in {build_time:.1f}s "
        f"(variant={method_name})"
    )
    logger.info(f"  Graph: {g.vcount():,} nodes, {g.ecount():,} edges")
    del graph

    return _score_detect_graph(
        method_name=method_name,
        dataset="LANL-2015",
        g=g,
        red_pairs=red_pairs,
        build_time=build_time,
        total_events=n_auth + n_flow,
        config=config,
        output_dir=output_dir,
    )
