"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import igraph as ig
import pandas as pd

from src.data_loader import (
    AUTH_COLUMNS,
    AUTH_NUMERIC,
    FLOW_COLUMNS,
    FLOW_NUMERIC,
    _build_window_intervals,
    load_redteam,
)
from src.detection import compute_pair_metrics, optimize_threshold
from src.features import extract_all_features
from src.graph_builder import StreamingGraphBuilder, stream_gz_to_graph
from src.scorer import boost_edges_from_paths, score_edges, score_graph, score_paths

logger = logging.getLogger(__name__)


def _mp_run_lanl_baselines(
    results_dir: str, red_pairs_list: list[tuple[str, str]], config: dict
) -> list[dict]:
    """Top-level function for multiprocessing: load data from disk, run LANL baselines."""
    import logging as _logging

    _log = _logging.getLogger(__name__)

    ef_path = Path(results_dir) / "combined" / "edge_features.csv"
    edges_path = Path(results_dir) / "combined" / "graph_edges.csv"
    if not ef_path.exists():
        _log.warning("LANL baselines: edge_features.csv not found")
        return []

    edge_features = pd.read_csv(ef_path)
    red_pairs = set(red_pairs_list)

    # Build edge_pair_names from graph_edges.csv (avoid needing igraph object)
    if edges_path.exists():
        edges_df = pd.read_csv(edges_path)
        edge_pair_names = list(zip(edges_df["src"].astype(str), edges_df["dst"].astype(str)))
    else:
        # Fallback: derive from edge_features index (less reliable)
        _log.warning("LANL baselines: graph_edges.csv not found, using edge_features index")
        return []

    import numpy as np

    from src.baselines.shared_baselines import SCORING_FEATURE_COLUMNS

    available = [c for c in SCORING_FEATURE_COLUMNS if c in edge_features.columns]
    if not available:
        return []

    mask = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )
    features = edge_features[available].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    labels = np.array([1.0 if pair in red_pairs else 0.0 for pair in edge_pair_names])

    features_valid = features[mask]
    labels_valid = labels[mask]
    _log.info(f"LANL baselines: {len(features_valid):,} edges, {available} features")

    from src.baselines.shared_baselines import run_baselines

    baseline_results = run_baselines(features_valid, labels_valid, config)
    return [
        {
            "method": r["method"],
            "dataset": "LANL-2015",
            "recall": round(r["recall"], 4),
            "fpr": round(r["fpr"], 4),
            "f1": round(r["f1"], 4),
            "auc": round(r["auc"], 4),
            "latency": 0.0,
            "throughput": 0.0,
        }
        for r in baseline_results
    ]


def _mp_run_dapt_baselines(dapt_dir: str, max_events: int | None, config: dict) -> list[dict]:
    """Top-level function for multiprocessing: run DAPT2020 baselines."""
    import logging as _logging

    _log = _logging.getLogger(__name__)
    from src.baselines.dapt_baselines import run_dapt_baselines

    dapt_results = run_dapt_baselines(data_dir=dapt_dir, max_rows=max_events, config=config)
    return [
        {
            "method": r["method"],
            "dataset": "DAPT2020",
            "recall": round(r["recall"], 4),
            "fpr": round(r["fpr"], 4),
            "f1": round(r["f1"], 4),
            "auc": round(r["auc"], 4),
            "latency": 0.0,
            "throughput": 0.0,
        }
        for r in dapt_results
    ]


def _mp_run_dapt_graph(dapt_dir: str, max_events: int | None, config: dict) -> list[dict]:
    """Top-level function for multiprocessing: run DAPT2020 graph method."""
    import logging as _logging

    _log = _logging.getLogger(__name__)
    from src.baselines.dapt_graph import run_dapt_graph

    result = run_dapt_graph(data_dir=dapt_dir, max_rows=max_events, config=config)
    return [result]


def run_streaming_experiment(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    dapt_dir: str = "data/DAPT2020",
    max_events: int | None = None,
    config: dict | None = None,
) -> tuple[list[dict], dict, str]:
    from datetime import datetime, timezone

    _cfg = config or {}
    scoring_cfg = _cfg.get("scoring", {})
    graph_cfg = _cfg.get("graph", {})
    feat_cfg = _cfg.get("features", {})

    threshold_percentile = scoring_cfg.get("threshold_percentile", 90)
    progress_every = graph_cfg.get("progress_every", 500000)
    max_hops = scoring_cfg.get("max_hops", 4)
    top_k_paths = scoring_cfg.get("top_k_paths", 50)
    top_outgoing = scoring_cfg.get("top_outgoing_per_node", 10)
    max_workers = feat_cfg.get("max_workers", 12)
    weights = scoring_cfg.get("weights", {"is_ntlm": 0.4, "is_network_logon": 0.3, "edge_rarity": 0.3})

    data_path = Path(data_dir)
    all_results: list[dict] = []
    viz_data: dict = {}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_base = Path("results") / run_id
    results_base.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, output dir: {results_base}")

    with open(results_base / "pipeline_config.json", "w") as f:
        json.dump(_cfg, f, indent=2)
    logger.info(f"  Saved pipeline_config.json to {results_base}")

    rt = load_redteam(str(data_path / "redteam.txt.gz"))
    red_pairs = set(zip(rt["src_comp"].astype(str), rt["dst_comp"].astype(str)))
    windows = _build_window_intervals(rt, window_seconds)
    logger.info(f"Red team: {len(rt)} events, {len(windows)} merged windows")
    viz_data["redteam_times"] = rt["time"]
    viz_data["red_pairs"] = red_pairs
    method_graphs: dict[str, ig.Graph | None] = {}

    redteam_dir = results_base / "redteam"
    redteam_dir.mkdir(parents=True, exist_ok=True)
    rt.to_csv(redteam_dir / "redteam_events.csv", index=False)
    with open(redteam_dir / "window_intervals.json", "w") as f:
        json.dump([{"start": s, "end": e} for s, e in windows], f, indent=2)
    with open(redteam_dir / "redteam_pairs.json", "w") as f:
        json.dump([{"src": s, "dst": d} for s, d in sorted(red_pairs)], f, indent=2)
    logger.info(f"  Saved redteam data to {redteam_dir}")

    for method_name, feed_auth, feed_flow in [
        ("flow_only", None, True),
        ("auth_only", True, None),
        ("combined", True, True),
    ]:
        logger.info(f"Streaming + building: {method_name}")
        t0 = time.perf_counter()

        graph = StreamingGraphBuilder()

        if feed_auth:
            n_auth = stream_gz_to_graph(
                str(data_path / "auth.txt.gz"),
                AUTH_COLUMNS, windows, AUTH_NUMERIC,
                graph, graph.feed_auth_event,
                progress_every=progress_every,
                max_events=max_events,
            )
        else:
            n_auth = 0

        if feed_flow:
            n_flow = stream_gz_to_graph(
                str(data_path / "flows.txt.gz"),
                FLOW_COLUMNS, windows, FLOW_NUMERIC,
                graph, graph.feed_flow_event,
                progress_every=progress_every,
                max_events=max_events,
            )
        else:
            n_flow = 0

        g = graph.build()
        build_time = time.perf_counter() - t0
        logger.info(
            f"  Streamed {n_auth:,} auth + {n_flow:,} flow in {build_time:.1f}s"
        )
        logger.info(f"  Graph: {g.vcount():,} nodes, {g.ecount():,} edges")

        del graph

        graph_edges = set()
        for e in g.es:
            graph_edges.add((g.vs[e.source]["name"], g.vs[e.target]["name"]))
        rt_in_graph = red_pairs & graph_edges
        logger.info(f"  Red team pairs in graph: {len(rt_in_graph)}/{len(red_pairs)}")

        t1 = time.perf_counter()
        logger.info(f"  Extracting features ({g.vcount():,} nodes, {g.ecount():,} edges)...")
        all_feat = extract_all_features(g, config=_cfg)
        logger.info(f"  Features extracted in {time.perf_counter() - t1:.1f}s, scoring edges...")
        edge_scores = score_edges(g, all_feat["edge_features"], weights=weights, config=_cfg)
        logger.info("  Edge scores computed, enumerating paths (this may take a while)...")
        paths = score_paths(g, edge_scores, max_hops=max_hops, top_k=top_k_paths, top_outgoing=top_outgoing, max_workers=max_workers)
        logger.info(f"  Scored {len(paths):,} paths, computing graph-level scores...")

        path_boost_factor = scoring_cfg.get("path_boost_factor", 0.1)
        edge_scores = boost_edges_from_paths(edge_scores, paths, boost_factor=path_boost_factor)
        logger.info(f"  Applied path boost (factor={path_boost_factor})")
        graph_result = score_graph(g, all_feat, edge_scores, paths=paths)
        score_time = time.perf_counter() - t1
        logger.info(f"  Scoring completed in {score_time:.1f}s")

        ef = all_feat["edge_features"]
        mask_valid = (
            (ef["is_self_loop"].values == 0.0)
            & (ef["is_user_edge"].values == 0.0)
        )

        edge_pair_names = [
            (g.vs[g.es[i].source]["name"], g.vs[g.es[i].target]["name"])
            for i in range(g.ecount())
        ]

        threshold_mode = scoring_cfg.get("threshold_mode", "auto_optimize")
        threshold_search_range = scoring_cfg.get("threshold_search_range", [90, 95, 97, 99, 99.5, 99.9])

        threshold, best_pct = optimize_threshold(
            edge_scores, mask_valid, edge_pair_names,
            rt_in_graph, red_pairs,
            threshold_mode=threshold_mode,
            search_range=threshold_search_range,
            default_percentile=threshold_percentile,
        )

        metrics = compute_pair_metrics(
            edge_scores, mask_valid, edge_pair_names,
            graph_edges, rt_in_graph, red_pairs,
            threshold,
        )

        total_events = n_auth + n_flow
        result = {
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
            "threshold_mode": threshold_mode,
            "threshold_percentile_used": best_pct if threshold_mode == "auto_optimize" else threshold_percentile,
            "max_path_score": round(graph_result["max_path_score"], 4),
            "mean_edge_score": round(graph_result["mean_edge_score"], 4),
        }
        all_results.append(result)
        logger.info(
            f"  {method_name}: recall={metrics['recall']:.4f}, fpr={metrics['fpr']:.4f}, f1={metrics['f1']:.4f}"
        )

        anomalous_pairs = metrics["anomalous_pairs"]
        detected_pairs = metrics["detected_pairs"]

        method_dir = results_base / method_name
        method_dir.mkdir(parents=True, exist_ok=True)

        edge_scores.to_csv(method_dir / "edge_scores.csv", header=["score"])
        logger.info(f"  Saved edge_scores.csv ({len(edge_scores):,} edges)")

        if len(paths) > 0:
            paths_save = paths.copy()
            paths_save["path_nodes"] = paths_save["path_nodes"].apply(lambda x: " -> ".join(x) if isinstance(x, list) else str(x))
            paths_save["path_edges"] = paths_save["path_edges"].apply(lambda x: ",".join(str(i) for i in x) if isinstance(x, list) else str(x))
            paths_save.to_csv(method_dir / "paths.csv", index=False)
            logger.info(f"  Saved paths.csv ({len(paths_save):,} paths)")

        if len(anomalous_pairs) > 0:
            ap_rows = [{"src": s, "dst": d} for s, d in anomalous_pairs]
            pd.DataFrame(ap_rows).to_csv(method_dir / "anomalous_paths.csv", index=False)
            logger.info(f"  Saved anomalous_paths.csv ({len(ap_rows):,} anomalous edges)")

        all_feat["node_features"].to_csv(method_dir / "node_features.csv")
        all_feat["edge_features"].to_csv(method_dir / "edge_features.csv")
        with open(method_dir / "graph_features.json", "w") as f:
            json.dump(all_feat["graph_features"], f, indent=2)
        logger.info("  Saved node_features.csv, edge_features.csv, graph_features.json")

        edge_rows = []
        for e in g.es:
            attrs = e.attributes()
            edge_rows.append({
                "src": g.vs[e.source]["name"],
                "dst": g.vs[e.target]["name"],
                **{k: v for k, v in attrs.items() if k != "weight" or True},
            })
        pd.DataFrame(edge_rows).to_csv(method_dir / "graph_edges.csv", index=False)

        node_rows = [{"name": v["name"], **{k: v for k, v in v.attributes().items() if k != "name"}} for v in g.vs]
        pd.DataFrame(node_rows).to_csv(method_dir / "graph_nodes.csv", index=False)
        logger.info(f"  Saved graph_edges.csv ({g.ecount():,}), graph_nodes.csv ({g.vcount():,})")

        if detected_pairs:
            with open(method_dir / "detected_redteam_pairs.json", "w") as f:
                json.dump([{"src": s, "dst": d} for s, d in sorted(detected_pairs)], f, indent=2)
            logger.info(f"  Saved detected_redteam_pairs.json ({len(detected_pairs)} pairs)")

        if method_name == "combined":
            viz_data["combined_graph"] = g
            viz_data["combined_edge_scores"] = edge_scores
            viz_data["combined_paths"] = paths
            viz_data["combined_threshold"] = threshold
            viz_data["combined_edge_features"] = ef
        else:
            method_graphs[method_name] = None
            del g

    baseline_tasks: list[tuple[str, tuple]] = []

    if _cfg.get("baselines", {}).get("run_lanl_baselines", True) and "combined_graph" in viz_data:
        baseline_tasks.append(("lanl", (_mp_run_lanl_baselines, str(results_base), list(red_pairs), _cfg)))

    baseline_tasks.append(("dapt_bl", (_mp_run_dapt_baselines, dapt_dir, max_events, _cfg)))

    if _cfg.get("baselines", {}).get("run_dapt_graph", True):
        baseline_tasks.append(("dapt_graph", (_mp_run_dapt_graph, dapt_dir, max_events, _cfg)))

    if baseline_tasks:
        logger.info(f"Running all baselines in parallel ({len(baseline_tasks)} tasks)")
        with ProcessPoolExecutor(max_workers=len(baseline_tasks)) as pool:
            futures = {}
            for name, (fn, *args) in baseline_tasks:
                futures[pool.submit(fn, *args)] = name
            for future in as_completed(futures):
                name = futures[future]
                try:
                    results = future.result()
                    all_results.extend(results)
                    logger.info(f"  {name}: completed with {len(results)} results")
                except Exception as e:
                    logger.warning(f"  {name}: failed: {e}")

    viz_data["method_graphs"] = method_graphs
    return all_results, viz_data, str(results_base)
