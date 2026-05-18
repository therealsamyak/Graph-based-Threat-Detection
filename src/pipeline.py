"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import json
import logging
import time
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.io import save_method_results, save_pipeline_config, save_redteam_data
from src.stages import load_redteam_data, run_method_pipeline
from src.types import ExperimentResult, PipelineConfig

logger = logging.getLogger(__name__)


def generate_run_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def get_base_output_dir(run_id: str) -> Path:
    return Path("results") / run_id


def get_output_dir(run_id: str, variant: str = "combined") -> Path:
    return get_base_output_dir(run_id) / "LANL-2015" / variant


def init_output_dirs(run_id: str) -> Path:
    base_dir = get_base_output_dir(run_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, output dir: {base_dir}")
    return base_dir


def run_streaming_experiment(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: dict | PipelineConfig | None = None,
    run_id: str | None = None,
    variant: str = "combined",
) -> tuple[list[dict], dict, str]:
    """Run streaming experiment for a single variant.

    Args:
        data_dir: Path to LANL dataset directory
        window_seconds: Time window for red team merging (seconds)
        max_events: Max events to process (None = all)
        config: Pipeline configuration (dict or PipelineConfig)
        run_id: Explicit run ID (generated if None)
        variant: Variant name for output subdir (default: "combined")

    Returns:
        (method_results, experiment_result_dict, base_results_dir_path)
    """
    if isinstance(config, PipelineConfig):
        cfg = config
    else:
        cfg = PipelineConfig.from_dict(config) if config else PipelineConfig.default()

    if run_id is None:
        run_id = generate_run_id()

    results_base = init_output_dirs(run_id)

    save_pipeline_config(str(results_base), cfg)

    pipeline_start = time.perf_counter()

    rt, red_pairs, windows = load_redteam_data(data_dir, window_seconds)
    save_redteam_data(str(results_base), rt, red_pairs, windows)

    mr = run_method_pipeline(
        data_dir=data_dir,
        windows=windows,
        red_pairs=red_pairs,
        config=cfg,
        max_events=max_events,
        output_dir=str(get_output_dir(run_id, variant)),
        variant=variant,
    )

    save_method_results(
        output_dir=str(get_output_dir(run_id, variant)),
        method=variant,
        g=mr.graph,
        edge_scores=mr.edge_scores,
        paths=mr.paths,
        edge_features=mr.edge_features,
        node_features=mr.node_features,
        graph_features=mr.graph_features,
        anomalous_pairs=mr.metrics["anomalous_pairs"],
        detected_pairs=mr.metrics["detected_pairs"],
    )

    all_results = [mr.result_dict]

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
        },
        "timing": {
            "build_time": mr.build_time,
            "score_time": mr.score_time,
            "total_duration": total_duration,
        },
        "intermediate": {
            "threshold": mr.threshold,
            "red_team_pairs_count": len(red_pairs),
        },
        "final_metrics": {
            "LANL-2015": mr.result_dict,
        },
        "feature_stats": {},
    }

    if mr.edge_features is not None:
        edge_feat_df = mr.edge_features
        pipeline_run["feature_stats"] = {
            "shape": list(edge_feat_df.shape),
            "columns": list(edge_feat_df.columns),
            "nan_counts": edge_feat_df.isna().sum().to_dict(),
        }

    with open(results_base / "pipeline_run.json", "w") as f:
        json.dump(pipeline_run, f, indent=2, default=str)
    logger.info(f"[{variant}] Saved pipeline_run.json to {results_base}")

    logger.info(f"Pipeline completed in {total_duration:.2f}s (variant={variant})")
    logger.info(f"  [{variant}] Recall: {mr.metrics.get('recall'):.4f}, F1: {mr.metrics.get('f1'):.4f}, FPR: {mr.metrics.get('fpr'):.6f}")

    return all_results, asdict(experiment_result), str(results_base)


def run_streaming_experiment_variants(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: PipelineConfig | None = None,
) -> tuple[list[dict], str, dict | None]:
    """Run all variants sequentially.

    Each variant (auth_only, combined, flow_only) runs one after another.
    Inner parallelism (node features, path scoring) is preserved within each variant.

    Args:
        data_dir: Path to LANL dataset directory.
        window_seconds: Time window for red team merging.
        max_events: Max events per source (None = all).
        config: Pipeline configuration (uses default if None).

    Returns:
        (all_method_result_rows, results_base_dir_path, combined_result_dict)
    """
    from src.variants import get_all_descriptors

    if config is None:
        config = PipelineConfig.default()

    descriptors = get_all_descriptors()

    run_id = generate_run_id()
    results_base = str(get_base_output_dir(run_id))

    variant_names = [d.name for d in descriptors]
    logger.info(f"Running {len(variant_names)} variants sequentially: {', '.join(variant_names)}")

    all_results: list[dict] = []
    experiment_results_by_variant: dict[str, dict] = {}
    overall_start = time.perf_counter()

    for i, descriptor in enumerate(descriptors, 1):
        logger.info(f"── Variant {i}/{len(descriptors)}: {descriptor.name} ──")
        try:
            variant_results, variant_experiment_result, _ = run_streaming_experiment(
                data_dir=data_dir,
                window_seconds=window_seconds,
                max_events=max_events,
                config=config,
                run_id=run_id,
                variant=descriptor.name,
            )
            all_results.extend(variant_results)
            experiment_results_by_variant[descriptor.name] = variant_experiment_result
        except Exception as exc:
            logger.error(f"Variant '{descriptor.name}' failed: {exc}")
            raise

    total_duration = time.perf_counter() - overall_start
    logger.info(f"All {len(variant_names)} variants completed in {total_duration:.2f}s")

    combined_result = experiment_results_by_variant.get("combined")
    return all_results, results_base, combined_result
