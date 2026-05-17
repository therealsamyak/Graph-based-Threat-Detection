"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import json
import logging
import multiprocessing
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from src.io import save_method_results, save_pipeline_config, save_redteam_data
from src.stages import load_redteam_data, run_method_pipeline
from src.types import ExperimentResult, PipelineConfig
from src.utils import compute_inner_worker_budget

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


def _terminate_processes(
    processes: list[multiprocessing.process.BaseProcess],
    timeout: float = 5.0,
) -> None:
    for p in processes:
        if p.is_alive():
            logger.warning(f"Terminating live process: {p.name} (pid={p.pid})")
            p.terminate()

    for p in processes:
        p.join(timeout=timeout)
        if p.is_alive():
            logger.error(f"Process {p.name} (pid={p.pid}) did not exit after terminate+timeout")
            p.kill()
            p.join()



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


# ── Multiprocessing variant orchestration ──────────────────────────────────────


def _variant_worker(
    variant: str,
    data_dir: str,
    window_seconds: int,
    max_events: int | None,
    config: PipelineConfig,
    run_id: str,
    result_queue: multiprocessing.Queue,
) -> None:
    """Worker target for one variant (pickle-safe under spawn)."""
    try:
        logger.info(f"Child worker START: variant={variant}, run_id={run_id}")
        all_results, experiment_result_dict, _results_base = run_streaming_experiment(
            data_dir=data_dir,
            window_seconds=window_seconds,
            max_events=max_events,
            config=config,
            run_id=run_id,
            variant=variant,
        )
        logger.info(f"Child worker DONE: variant={variant}")
        result_queue.put(("ok", (all_results, experiment_result_dict)))
        result_queue.close()
        result_queue.join_thread()
    except Exception as exc:
        logger.error(f"Child worker FAILED: variant={variant}, error={exc}")
        try:
            result_queue.put(("error", str(exc)))
            result_queue.close()
            result_queue.join_thread()
        except Exception:
            pass
        raise SystemExit(1)


def run_streaming_experiment_variants(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: PipelineConfig | None = None,
) -> tuple[list[dict], str, dict | None]:
    """Run all variants in parallel via multiprocessing spawn.

    Args:
        data_dir: Path to LANL dataset directory.
        window_seconds: Time window for red team merging.
        max_events: Max events per source (None = all).
        config: Pipeline configuration (uses default if None).

    Returns:
        (all_method_result_rows, results_base_dir_path, combined_result_dict)

    Raises:
        RuntimeError: If any child process fails or exits nonzero.
        KeyboardInterrupt: Re-raised after cleaning up child processes.
    """
    from src.variants import get_all_descriptors

    if config is None:
        config = PipelineConfig.default()

    run_id = generate_run_id()

    inner_workers = compute_inner_worker_budget(num_top_level_variants=3)
    capped_features = replace(config.features, inner_workers=inner_workers)
    config_capped = replace(config, features=capped_features)

    logger.info(
        f"Parent spawning 3 variant workers: run_id={run_id}, "
        f"inner_workers={inner_workers}"
    )

    descriptors = get_all_descriptors()
    variant_names = [d.name for d in descriptors]

    ctx = multiprocessing.get_context("spawn")

    processes: list[multiprocessing.process.BaseProcess] = []
    result_queues: list[multiprocessing.Queue] = []

    for variant in variant_names:
        q: multiprocessing.Queue = ctx.Queue()
        result_queues.append(q)

        p = ctx.Process(
            target=_variant_worker,
            args=(variant, data_dir, window_seconds, max_events, config_capped, run_id, q),
            name=f"variant-{variant}",
        )
        processes.append(p)

    # Start all children
    for p in processes:
        p.start()

    _LAST_RESORT_TIMEOUT_S = 8 * 60 * 60  # 8h (observed max: ~3h for combined)    _LAST_RESORT_TIMEOUT_S = 8 * 60 * 60  # 8h (observed max: ~3h for combined)
    try:
        deadline = time.monotonic() + _LAST_RESORT_TIMEOUT_S
        while any(p.is_alive() for p in processes):
            time.sleep(0.1)
            for p in processes:
                if not p.is_alive() and p.exitcode != 0:
                    logger.error(
                        f"Early failure detected: {p.name} exited with code {p.exitcode} "
                        f"while siblings are still alive"
                    )
                    _terminate_processes(processes)
                    raise RuntimeError(
                        f"Variant worker '{p.name}' failed early with exitcode={p.exitcode} "
                        f"while sibling processes were still running"
                    )
            if time.monotonic() > deadline:
                logger.error(
                    f"Last-resort timeout: workers still alive after {_LAST_RESORT_TIMEOUT_S}s, "
                    f"force-terminating"
                )
                _terminate_processes(processes)
                raise RuntimeError(
                    f"Variant workers did not exit after {_LAST_RESORT_TIMEOUT_S}s "
                    f"(queue cleanup may have failed)"
                )

        for p in processes:
            p.join()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received - terminating variant workers")
        _terminate_processes(processes)
        raise

    all_results: list[dict] = []
    failed_variants: list[str] = []
    experiment_results_by_variant: dict[str, dict] = {}

    for variant, p, q in zip(variant_names, processes, result_queues):
        if p.exitcode != 0:
            failed_variants.append(f"{variant} (exitcode={p.exitcode})")
            continue

        if q.empty():
            failed_variants.append(f"{variant} (no result returned)")
            continue

        status, payload = q.get()
        if status == "error":
            failed_variants.append(f"{variant} (error: {payload})")
            continue

        variant_results, variant_experiment_result = payload
        all_results.extend(variant_results)
        experiment_results_by_variant[variant] = variant_experiment_result

    for q in result_queues:
        q.close()

    if failed_variants:
        raise RuntimeError(
            f"Variant worker(s) failed: {', '.join(failed_variants)}"
        )

    results_base = str(get_base_output_dir(run_id))
    combined_result = experiment_results_by_variant.get("combined")
    return all_results, results_base, combined_result