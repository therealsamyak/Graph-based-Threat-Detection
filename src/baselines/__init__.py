"""Baselines package — SVM and Isolation Forest comparison with graph-based pipeline."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from src.baselines.comparison import build_comparison_table, load_graph_based_results
from src.baselines.data import _find_variant_dir, find_latest_run
from src.baselines.runner import build_summary, evaluate_variant
from src.baselines.types import VALID_VARIANTS

logger = logging.getLogger(__name__)


def run_baselines(
    results_dir: Path,
    output_dir: Path,
    run_id: str | None = None,
    variant: str | None = None,
) -> None:
    """Run baseline tests (SVM, Isolation Forest) on cached pipeline outputs.

    Args:
        results_dir: Directory containing cached run outputs.
        output_dir: Root directory for baseline results.
        run_id: Specific run_id to evaluate. Defaults to latest.
        variant: Specific variant to evaluate. Defaults to all found variants.
    """
    # ── Determine run directory ──
    if run_id:
        run_dir_path = results_dir / run_id
        if not run_dir_path.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir_path}")
    else:
        run_dir_path = find_latest_run(results_dir)
        logger.info(f"Using latest run: {run_dir_path.name}")

    # ── Determine variants to evaluate ──
    variants_to_eval: list[str] = []
    for v in VALID_VARIANTS:
        try:
            _find_variant_dir(run_dir_path, v)
            variants_to_eval.append(v)
        except FileNotFoundError:
            pass

    if variant:
        if variant not in variants_to_eval:
            raise FileNotFoundError(
                f"Variant '{variant}' not found in run {run_dir_path.name}. "
                f"Available: {variants_to_eval}"
            )
        variants_to_eval = [variant]

    if not variants_to_eval:
        raise FileNotFoundError(
            f"No valid variants found in {run_dir_path}. "
            f"Ensure the directory contains variant subdirectories with edge_features.csv."
        )

    logger.info(f"Evaluating variants: {variants_to_eval}")

    # ── Create output directory ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = output_dir / timestamp
    run_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {run_output_dir}")

    # ── Evaluate each variant ──
    per_variant_results: dict[str, dict] = {}
    graph_results: dict[str, dict | None] = {}

    for v in variants_to_eval:
        start_time = time.time()

        # Run baselines
        v_results = evaluate_variant(run_dir_path, v, run_output_dir)
        per_variant_results[v] = v_results

        # Load graph-based results for comparison
        graph = load_graph_based_results(run_dir_path, v)
        graph_results[v] = graph

        elapsed = time.time() - start_time
        logger.info(f"Completed {v} in {elapsed:.1f}s")

    # ── Build comparison table ──
    comparison_md = build_comparison_table(per_variant_results, graph_results)
    (run_output_dir / "comparison_table.md").write_text(comparison_md)
    logger.info(f"Saved {run_output_dir / 'comparison_table.md'}")

    # ── Build summary ──
    build_summary(
        variants_to_eval=variants_to_eval,
        per_variant_results=per_variant_results,
        graph_results=graph_results,
        run_id=run_dir_path.name,
        timestamp=timestamp,
        output_dir=run_output_dir,
    )

    # ── Print summary ──
    print(f"\n{'=' * 70}")
    print(f"Baseline testing complete: {run_output_dir}")
    print(f"Run ID: {run_dir_path.name}")
    print(f"{'=' * 70}")
    print(comparison_md)


__all__ = ["run_baselines"]
