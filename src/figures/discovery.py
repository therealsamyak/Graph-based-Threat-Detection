"""Filesystem discovery helpers for latest pipeline artifacts."""

from __future__ import annotations

from pathlib import Path

from src.figures.style import logger


def find_latest_dir(base_dir: Path) -> Path | None:
    if not base_dir.is_dir():
        logger.warning("Directory not found: %s", base_dir)
        return None
    dirs = sorted(
        [d for d in base_dir.iterdir() if d.is_dir() and d.name != "pending"],
        key=lambda d: d.name,
        reverse=True,
    )
    if not dirs:
        logger.warning("No subdirectories found in %s", base_dir)
        return None
    return dirs[0]


def find_latest_results(run_id: str | None) -> Path | None:
    if run_id is not None:
        target = Path("results") / "pipeline" / run_id
        if target.is_dir():
            return target
        logger.warning("Specified run-id directory not found: %s", target)
        return None
    return find_latest_dir(Path("results") / "pipeline")


def find_latest_feature_audit() -> Path | None:
    return find_latest_dir(Path("results") / "feature_audit")


def find_latest_analysis() -> Path | None:
    return find_latest_dir(Path("results") / "analysis")


def find_latest_baselines() -> Path | None:
    return find_latest_dir(Path("results") / "baselines")
