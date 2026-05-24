"""Baselines package — SVM and Isolation Forest comparison with graph-based pipeline."""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path

from src.baselines.comparison import build_comparison_table, load_graph_based_results
from src.baselines.data import find_latest_run, find_variant_dir
from src.baselines.figures import generate_baseline_figures
from src.baselines.runner import GraphResults, VariantResults, build_summary, evaluate_variant
from src.variants import list_variants

logger = logging.getLogger(__name__)


def run_baselines(
    results_dir: Path,
    output_dir: Path,
    run_id: str | None = None,
    variant: str | None = None,
) -> None:
    """Run baseline tests (SVM, Isolation Forest) on cached pipeline outputs."""
    if run_id:
        run_dir_path = results_dir / run_id
        if not run_dir_path.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir_path}")
    else:
        run_dir_path = find_latest_run(results_dir)
        logger.info(f"Using latest run: {run_dir_path.name}")

    variants_to_eval: list[str] = []
    for candidate in list_variants():
        try:
            find_variant_dir(run_dir_path, candidate)
            variants_to_eval.append(candidate)
        except FileNotFoundError:
            logger.debug(f"Variant '{candidate}' not found in {run_dir_path}")

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

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    run_output_dir = output_dir / timestamp
    run_output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {run_output_dir}")

    per_variant_results: dict[str, VariantResults] = {}
    graph_results: GraphResults = {}

    for candidate in variants_to_eval:
        start_time = time.time()

        variant_results = evaluate_variant(run_dir_path, candidate, run_output_dir)
        per_variant_results[candidate] = variant_results

        graph = load_graph_based_results(run_dir_path, candidate)
        graph_results[candidate] = graph

        elapsed = time.time() - start_time
        logger.info(f"Completed {candidate} in {elapsed:.1f}s")

    comparison_md = build_comparison_table(per_variant_results, graph_results)
    (run_output_dir / "comparison_table.md").write_text(comparison_md)
    logger.info(f"Saved {run_output_dir / 'comparison_table.md'}")

    build_summary(
        variants_to_eval=variants_to_eval,
        per_variant_results=per_variant_results,
        graph_results=graph_results,
        run_id=run_dir_path.name,
        timestamp=timestamp,
        output_dir=run_output_dir,
    )

    figures_dir = generate_baseline_figures(run_output_dir, results_dir)
    logger.info(f"Saved baseline figures in {figures_dir}")

    print(f"\n{'=' * 70}")
    print(f"Baseline testing complete: {run_output_dir}")
    print(f"Run ID: {run_dir_path.name}")
    print(f"{'=' * 70}")
    print(comparison_md)


__all__ = ["run_baselines"]
