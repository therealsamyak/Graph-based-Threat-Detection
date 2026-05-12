"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from src.io import save_method_results, save_pipeline_config, save_redteam_data
from src.stages import load_redteam_data, run_method_pipeline
from src.types import ExperimentResult, PipelineConfig
logger = logging.getLogger(__name__)


def _mp_run_lanl_baselines(
    results_dir: str, red_pairs_list: list[tuple[str, str]], config: dict
) -> list[dict]:
    import logging as _logging
    import pandas as pd
    _log = _logging.getLogger(__name__)

    ef_path = Path(results_dir) / "combined" / "edge_features.csv"
    edges_path = Path(results_dir) / "combined" / "graph_edges.csv"
    if not ef_path.exists():
        _log.warning("LANL baselines: edge_features.csv not found")
        return []

    edge_features = pd.read_csv(ef_path)
    red_pairs = set(red_pairs_list)

    if edges_path.exists():
        edges_df = pd.read_csv(edges_path)
        edge_pair_names = list(zip(edges_df["src"].astype(str), edges_df["dst"].astype(str)))
    else:
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
    config: dict | PipelineConfig | None = None,
) -> tuple[list[dict], dict, str]:
    if isinstance(config, PipelineConfig):
        cfg = config
    else:
        cfg = PipelineConfig.from_dict(config) if config else PipelineConfig.default()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_base = Path("results") / run_id
    results_base.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, output dir: {results_base}")

    save_pipeline_config(str(results_base), cfg)

    rt, red_pairs, windows = load_redteam_data(data_dir, window_seconds)
    save_redteam_data(str(results_base), rt, red_pairs, windows)

    combined_graph = None
    combined_edge_scores = None
    combined_paths = None
    combined_threshold = 0.0
    combined_edge_features = None
    method_graphs: dict[str, object | None] = {}
    all_results: list[dict] = []

    for method_name, feed_auth, feed_flow in [
        ("flow_only", None, True),
        ("auth_only", True, None),
        ("combined", True, True),
    ]:
        mr = run_method_pipeline(
            method_name=method_name,
            data_dir=data_dir,
            windows=windows,
            red_pairs=red_pairs,
            config=cfg,
            max_events=max_events,
            feed_auth=feed_auth,
            feed_flow=feed_flow,
        )

        all_results.append(mr.result_dict)

        save_method_results(
            output_dir=str(results_base / method_name),
            method=method_name,
            g=mr.graph,
            edge_scores=mr.edge_scores,
            paths=mr.paths,
            edge_features=mr.edge_features,
            node_features=mr.node_features,
            graph_features=mr.graph_features,
            anomalous_pairs=mr.metrics["anomalous_pairs"],
            detected_pairs=mr.metrics["detected_pairs"],
        )

        if method_name == "combined":
            combined_graph = mr.graph
            combined_edge_scores = mr.edge_scores
            combined_paths = mr.paths
            combined_threshold = mr.threshold
            combined_edge_features = mr.edge_features
        else:
            method_graphs[method_name] = None
            # mr (namedtuple) goes out of scope on next iteration, freeing graph

    baseline_tasks: list[tuple[str, tuple]] = []
    cfg_dict = cfg.to_dict()

    if cfg.baselines.run_lanl_baselines and combined_graph is not None:
        baseline_tasks.append(("lanl", (_mp_run_lanl_baselines, str(results_base), list(red_pairs), cfg_dict)))

    baseline_tasks.append(("dapt_bl", (_mp_run_dapt_baselines, dapt_dir, max_events, cfg_dict)))

    if cfg.baselines.run_dapt_graph:
        baseline_tasks.append(("dapt_graph", (_mp_run_dapt_graph, dapt_dir, max_events, cfg_dict)))

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

    experiment_result = ExperimentResult(
        combined_graph=combined_graph,
        combined_edge_scores=combined_edge_scores,
        combined_paths=combined_paths,
        combined_threshold=combined_threshold,
        combined_edge_features=combined_edge_features,
        red_pairs=frozenset(red_pairs),
        redteam_times=rt["time"],
        method_results=tuple(all_results),
        method_graphs=frozenset(method_graphs.keys()),
    )
    return all_results, experiment_result, str(results_base)
