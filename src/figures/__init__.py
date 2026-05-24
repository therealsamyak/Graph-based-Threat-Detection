"""Figure generation package API and orchestration."""

# pyright: reportMissingTypeArgument=false, reportArgumentType=false

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from src.figures.detection import (
    plot_detection_timeline,
    plot_graph_statistics,
    plot_holdout_validation,
    plot_score_distributions,
)
from src.figures.discovery import (
    find_latest_analysis,
    find_latest_baselines,
    find_latest_feature_audit,
    find_latest_results,
)
from src.figures.features import plot_ablation, plot_feature_audit, plot_feature_sweep
from src.figures.loading import (
    load_analysis_results,
    load_baseline_summary,
    load_feature_audit,
    load_metrics,
    load_run_metadata,
)
from src.figures.methods import plot_method_comparison, plot_radar_chart, plot_roc_curves
from src.figures.style import apply_paper_style, logger


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate paper-quality figures from pipeline results"
    )
    parser.add_argument(
        "--run-id",
        type=str,
        default=None,
        help="Target specific pipeline run directory name (default: auto-discover latest)",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="figures",
        help="Output directory for PNG figures (default: figures/)",
    )
    return parser.parse_args()


def discover_all(run_id: str | None) -> dict[str, Path | None]:
    return {
        "results_dir": find_latest_results(run_id),
        "audit_dir": find_latest_feature_audit(),
        "analysis_dir": find_latest_analysis(),
        "baselines_dir": find_latest_baselines(),
    }


def load_all(sources: dict[str, Path | None]) -> dict[str, Any]:
    results_dir = sources.get("results_dir")
    audit_dir = sources.get("audit_dir")
    analysis_dir = sources.get("analysis_dir")
    baselines_dir = sources.get("baselines_dir")

    metrics_df = load_metrics(results_dir) if results_dir else None
    _run_metadata = load_run_metadata(results_dir) if results_dir else None  # noqa: F841 — reserved for future figures
    audit_data = load_feature_audit(audit_dir) if audit_dir else None
    analysis_data = load_analysis_results(analysis_dir) if analysis_dir else None
    baseline_summary = load_baseline_summary(baselines_dir) if baselines_dir else None

    logger.info(
        "Data sources: results=%s, audit=%s, analysis=%s, baselines=%s",
        results_dir is not None,
        audit_dir is not None,
        analysis_dir is not None,
        baselines_dir is not None,
    )

    return {
        "results_dir": results_dir,
        "metrics_df": metrics_df,
        "audit_data": audit_data,
        "analysis_data": analysis_data,
        "baseline_summary": baseline_summary,
    }


def generate_all(data: dict[str, Any], output_dir: Path) -> None:
    metrics_df = data.get("metrics_df")
    baseline_summary = data.get("baseline_summary")
    audit_data = data.get("audit_data")
    analysis_data = data.get("analysis_data")
    results_dir = data.get("results_dir")

    generated = 0
    skipped = 0

    figures = [
        ("Method Comparison", lambda: plot_method_comparison(metrics_df, baseline_summary, output_dir)),
        ("ROC Curves", lambda: plot_roc_curves(metrics_df, baseline_summary, output_dir)),
        ("Radar Chart", lambda: plot_radar_chart(metrics_df, baseline_summary, output_dir)),
        ("Feature Audit", lambda: plot_feature_audit(audit_data, output_dir)),
        ("Ablation", lambda: plot_ablation(analysis_data, output_dir)),
        ("Feature Sweep", lambda: plot_feature_sweep(analysis_data, output_dir)),
        ("Score Distributions", lambda: plot_score_distributions(results_dir, output_dir)),
        ("Detection Timeline", lambda: plot_detection_timeline(results_dir, output_dir)),
        ("Graph Statistics", lambda: plot_graph_statistics(results_dir, output_dir)),
        ("Holdout Validation", lambda: plot_holdout_validation(analysis_data, output_dir)),
    ]

    for name, fn in figures:
        try:
            fn()
            logger.info("✓ Generated: %s", name)
            generated += 1
        except Exception as exc:
            logger.warning("✗ Skipped: %s (%s)", name, exc)
            skipped += 1

    logger.info("Complete: %d generated, %d skipped", generated, skipped)
    logger.info("Figure generation complete. Output: %s/", output_dir)


__all__ = [
    "apply_paper_style",
    "discover_all",
    "load_all",
    "generate_all",
    "parse_args",
    "plot_method_comparison",
    "plot_roc_curves",
    "plot_radar_chart",
    "plot_feature_audit",
    "plot_ablation",
    "plot_feature_sweep",
    "plot_score_distributions",
    "plot_detection_timeline",
    "plot_graph_statistics",
    "plot_holdout_validation",
]
