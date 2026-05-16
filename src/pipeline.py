"""Pipeline orchestrator: stream, build, score, detect, save."""

from __future__ import annotations

import json
import logging
import multiprocessing
import shutil
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
    """Generate a unique run ID using UTC timestamp.

    Returns:
        Run ID in format YYYYMMDD_HHMMSS
    """
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def get_base_output_dir(run_id: str) -> Path:
    """Get the base results directory for a given run ID.

    Args:
        run_id: Run ID string

    Returns:
        Path to results/<run_id>
    """
    return Path("results") / run_id


def get_output_dir(run_id: str, variant: str = "combined") -> Path:
    """Get the output directory for a specific variant within a run.

    Args:
        run_id: Run ID string
        variant: Variant name (e.g., "combined", "auth_only", "flow_only")

    Returns:
        Path to results/<run_id>/LANL-2015/<variant>
    """
    return get_base_output_dir(run_id) / "LANL-2015" / variant


def init_output_dirs(run_id: str) -> Path:
    """Initialize base output directories for a run.

    Creates the base results/<run_id> directory and returns the path.
    Does NOT create variant subdirectories - those are created per-variant
    when needed.

    Args:
        run_id: Run ID string

    Returns:
        Path to results/<run_id>
    """
    base_dir = get_base_output_dir(run_id)
    base_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, base output dir: {base_dir}")
    return base_dir


def _terminate_processes(
    processes: list[multiprocessing.process.BaseProcess],
    timeout: float = 5.0,
) -> None:
    """Terminate and join all processes in a list.

    Sends terminate() to each process, waits for them to exit using join()
    with timeout. Logs which processes did not exit cleanly.

    Args:
        processes: List of process objects to terminate
        timeout: Timeout in seconds for join() calls
    """
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


def safe_cleanup_smoke_results(captured_run_dir: str | Path) -> None:
    """Safely remove an explicitly captured smoke-test run directory.

    This helper enforces strict safety rules to prevent accidental deletion
    of user's pre-existing results. Only removes the exact path that was
    explicitly captured during smoke testing.

    Safety Rules:
    - Path must be an absolute path
    - Path must exist and be a directory
    - Path must start with the current working directory
    - Path must not be the project root or results/ parent
    - No filesystem scanning or "newest" inference

    Args:
        captured_run_dir: Explicitly captured path from smoke test

    Raises:
        ValueError: If path fails any safety check
        FileNotFoundError: If path does not exist
    """
    run_dir = Path(captured_run_dir)

    # Safety check 1: Must be absolute path (check original input before resolve)
    if not run_dir.is_absolute():
        raise ValueError(f"Safe cleanup requires absolute path, got: {captured_run_dir}")

    # Now resolve to get canonical form after confirming absolute
    run_dir = run_dir.resolve()

    # Safety check 2: Must exist and be a directory
    if not run_dir.exists():
        raise FileNotFoundError(f"Path does not exist: {run_dir}")
    if not run_dir.is_dir():
        raise ValueError(f"Path is not a directory: {run_dir}")

    # Safety check 3: Must be under current working directory
    cwd = Path.cwd().resolve()
    try:
        run_dir.relative_to(cwd)
    except ValueError:
        raise ValueError(f"Path is not under current working directory: {run_dir}")

    # Safety check 4: Must not be root or results parent directory
    if run_dir == cwd:
        raise ValueError(f"Refusing to delete current working directory: {run_dir}")
    if run_dir == (cwd / "results"):
        raise ValueError(f"Refusing to delete results parent directory: {run_dir}")

    # Safety check 5: Must be a run directory (results/<timestamp>)
    if run_dir.parent.name != "results" or run_dir.name.count("_") != 1:
        raise ValueError(
            f"Path does not match expected run directory pattern results/<timestamp>: {run_dir}"
        )

    # All safety checks passed - safe to remove
    logger.info(f"Safe cleanup: removing explicitly captured run directory: {run_dir}")
    shutil.rmtree(run_dir)
    logger.info(f"Safe cleanup: successfully removed: {run_dir}")


def run_streaming_experiment(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: dict | PipelineConfig | None = None,
    run_id: str | None = None,
    variant: str = "combined",
) -> tuple[list[dict], dict, str]:
    """Run streaming experiment with explicit run ID and variant support.

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

    # Generate or use provided run_id
    if run_id is None:
        run_id = generate_run_id()

    # Initialize base output directory (parent-owned)
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

    logger.info(f"Pipeline completed in {total_duration:.2f}s")
    logger.info(f"Recall: {mr.metrics.get('recall'):.4f}, F1: {mr.metrics.get('f1'):.4f}, FPR: {mr.metrics.get('fpr'):.6f}")

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
    """Module-level worker target for one variant (pickle-safe under spawn).

    Runs the variant pipeline and puts (status, payload) into result_queue.
    On success: ("ok", (all_results, experiment_result_dict)).
    On error: ("error", str).

    Args:
        variant: Variant name from descriptor registry.
        data_dir: Path to LANL dataset directory.
        window_seconds: Time window for red team merging.
        max_events: Max events per source (None = all).
        config: PipelineConfig with inner_workers already set.
        run_id: Shared run ID from parent.
        result_queue: Queue to report result or error back to parent.
    """
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
    except Exception as exc:
        logger.error(f"Child worker FAILED: variant={variant}, error={exc}")
        result_queue.put(("error", str(exc)))
        # Exit with nonzero code so parent early-failure polling detects this failure
        raise SystemExit(1)


def run_streaming_experiment_variants(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    max_events: int | None = None,
    config: PipelineConfig | None = None,
) -> tuple[list[dict], str, dict | None]:
    """Run all three variants in parallel via multiprocessing spawn.

    Spawns one child process per variant (combined, auth_only, flow_only).
    Parent generates a shared run_id and inner worker budget, then waits
    for all children. Raises if any child fails.

    Args:
        data_dir: Path to LANL dataset directory.
        window_seconds: Time window for red team merging.
        max_events: Max events per source (None = all).
        config: Pipeline configuration (uses default if None).

    Returns:
        (all_method_result_rows, results_base_dir_path, combined_result_dict)

        - all_method_result_rows: List of result dicts from all variants
        - results_base_dir_path: Path to results/<run_id>
        - combined_result_dict: ExperimentResult dict for combined variant (for combined-only visuals)

    Raises:
        RuntimeError: If any child process fails or exits nonzero.
        KeyboardInterrupt: Re-raised after cleaning up child processes.
    """
    from src.variants import get_all_descriptors

    if config is None:
        config = PipelineConfig.default()

    run_id = generate_run_id()

    # Compute inner worker budget for capped nested pools
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

    # Monitor children for early failure or KeyboardInterrupt
    try:
        # Poll processes while they run to detect early failures
        while any(p.is_alive() for p in processes):
            time.sleep(0.1)
            # Check if any process has exited with nonzero code while others are still alive
            for p in processes:
                if not p.is_alive() and p.exitcode != 0:
                    logger.error(
                        f"Early failure detected: {p.name} exited with code {p.exitcode} "
                        f"while siblings are still alive"
                    )
                    _terminate_processes(processes)
                    # Collect what we can and raise
                    raise RuntimeError(
                        f"Variant worker '{p.name}' failed early with exitcode={p.exitcode} "
                        f"while sibling processes were still running"
                    )

        # All processes have exited - join them to ensure clean reaping
        for p in processes:
            p.join()

    except KeyboardInterrupt:
        logger.info("KeyboardInterrupt received - terminating variant workers")
        _terminate_processes(processes)
        raise

    # Collect results and check for failures
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

    if failed_variants:
        raise RuntimeError(
            f"Variant worker(s) failed: {', '.join(failed_variants)}"
        )

    results_base = str(get_base_output_dir(run_id))
    combined_result = experiment_results_by_variant.get("combined")
    return all_results, results_base, combined_result