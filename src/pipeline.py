"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.io import save_method_results, save_pipeline_config, save_redteam_data
from src.stages import load_redteam_data, run_dapt_graph_pipeline, run_method_pipeline
from src.types import ExperimentResult, PipelineConfig

logger = logging.getLogger(__name__)


def run_streaming_experiment(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: dict | PipelineConfig | None = None,
) -> tuple[list[dict], dict, str]:
    """Run combined-only streaming experiment.

    Args:
        data_dir: Path to LANL dataset directory
        window_seconds: Time window for red team merging (seconds)
        max_events: Max events to process (None = all)
        config: Pipeline configuration (dict or PipelineConfig)

    Returns:
        (method_results, experiment_result_dict, results_dir_path)
    """
    if isinstance(config, PipelineConfig):
        cfg = config
    else:
        cfg = PipelineConfig.from_dict(config) if config else PipelineConfig.default()

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_base = Path("results") / run_id
    results_base.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, output dir: {results_base}")

    save_pipeline_config(str(results_base), cfg)

    pipeline_start = time.perf_counter()

    rt, red_pairs, windows = load_redteam_data(data_dir, window_seconds)
    save_redteam_data(str(results_base), rt, red_pairs, windows)

    # Single combined-only run
    mr = run_method_pipeline(
        data_dir=data_dir,
        windows=windows,
        red_pairs=red_pairs,
        config=cfg,
        max_events=max_events,
        output_dir=str(results_base / "LANL-2015" / "combined"),
    )

    # Save combined method results
    save_method_results(
        output_dir=str(results_base / "LANL-2015" / "combined"),
        method="combined",
        g=mr.graph,
        edge_scores=mr.edge_scores,
        paths=mr.paths,
        edge_features=mr.edge_features,
        node_features=mr.node_features,
        graph_features=mr.graph_features,
        anomalous_pairs=mr.metrics["anomalous_pairs"],
        detected_pairs=mr.metrics["detected_pairs"],
    )

    dapt_mr = run_dapt_graph_pipeline(
        dapt_dir=cfg.data.dapt_dir,
        config=cfg,
        output_dir=str(results_base / "DAPT2020" / "combined"),
    )
    save_method_results(
        output_dir=str(results_base / "DAPT2020" / "combined"),
        method="combined",
        g=dapt_mr.graph,
        edge_scores=dapt_mr.edge_scores,
        paths=dapt_mr.paths,
        edge_features=dapt_mr.edge_features,
        node_features=dapt_mr.node_features,
        graph_features=dapt_mr.graph_features,
        anomalous_pairs=dapt_mr.metrics["anomalous_pairs"],
        detected_pairs=dapt_mr.metrics["detected_pairs"],
    )

    all_results = [mr.result_dict, dapt_mr.result_dict]

    # Build ExperimentResult (method_graphs field removed in T2)
    experiment_result = ExperimentResult(
        combined_graph=mr.graph,
        combined_edge_scores=mr.edge_scores,
        combined_paths=mr.paths,
        combined_threshold=mr.threshold,
        combined_edge_features=mr.edge_features,
        red_pairs=frozenset(red_pairs),
        redteam_times=rt["time"],
        method_results=tuple(all_results),
    )

    pipeline_end = time.perf_counter()
    total_duration = pipeline_end - pipeline_start

    # Save pipeline_run.json with complete metadata
    pipeline_run = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "config": cfg.to_dict() if hasattr(cfg, "to_dict") else cfg.__dict__,
        "data_stats": {
            "data_dir": data_dir,
            "window_seconds": window_seconds,
            "lanl_total_events": mr.total_events,
            "lanl_graph_nodes": mr.graph.vcount(),
            "lanl_graph_edges": mr.graph.ecount(),
            "dapt_total_events": dapt_mr.total_events,
            "dapt_graph_nodes": dapt_mr.graph.vcount(),
            "dapt_graph_edges": dapt_mr.graph.ecount(),
        },
        "timing": {
            "build_time": mr.build_time,
            "score_time": mr.score_time,
            "total_duration": total_duration,
            "dapt_build_time": dapt_mr.build_time,
            "dapt_score_time": dapt_mr.score_time,
        },
        "intermediate": {
            "threshold": mr.threshold,
            "red_team_pairs_count": len(red_pairs),
        },
        "final_metrics": {
            "LANL-2015": mr.result_dict,
            "DAPT2020": dapt_mr.result_dict,
        },
        "feature_stats": {},
    }

    # Add feature statistics if available
    if mr.edge_features is not None:
        edge_feat_df = mr.edge_features
        pipeline_run["feature_stats"] = {
            "shape": list(edge_feat_df.shape),
            "columns": list(edge_feat_df.columns),
            "nan_counts": edge_feat_df.isna().sum().to_dict(),
        }

    # Save pipeline_run.json
    with open(results_base / "pipeline_run.json", "w") as f:
        json.dump(pipeline_run, f, indent=2, default=str)

    logger.info(f"Pipeline completed in {total_duration:.2f}s")
    logger.info(f"Recall: {mr.metrics.get('recall'):.4f}, F1: {mr.metrics.get('f1'):.4f}, FPR: {mr.metrics.get('fpr'):.6f}")

    return all_results, asdict(experiment_result), str(results_base)