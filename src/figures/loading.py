"""Data loading helpers for figure generation."""

# pyright: reportMissingTypeArgument=false

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from src.figures.style import logger


def load_metrics(results_dir: Path) -> pd.DataFrame | None:
    path = results_dir / "metrics.csv"
    if not path.exists():
        logger.warning("metrics.csv not found: %s", path)
        return None
    df = pd.read_csv(path)
    logger.info("Loaded metrics: %d rows from %s", len(df), path)
    return df


def load_run_metadata(results_dir: Path) -> dict | None:
    path = results_dir / "pipeline_run.json"
    if not path.exists():
        logger.warning("pipeline_run.json not found: %s", path)
        return None
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded run metadata from %s", path)
    return data


def load_feature_audit(audit_dir: Path) -> dict | None:
    path = audit_dir / "feature_audit_results.json"
    if not path.exists():
        logger.warning("feature_audit_results.json not found: %s", path)
        return None
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded feature audit from %s", path)
    return data


def load_analysis_results(analysis_dir: Path) -> dict | None:
    json_files = sorted(analysis_dir.glob("*.json"))
    if not json_files:
        logger.warning("No JSON files found in %s", analysis_dir)
        return None
    aggregated = {}
    for jf in json_files:
        with open(jf) as f:
            aggregated[jf.stem] = json.load(f)
    logger.info("Loaded %d analysis files from %s", len(json_files), analysis_dir)
    return aggregated


def load_baseline_summary(baselines_dir: Path) -> dict | None:
    path = baselines_dir / "summary.json"
    if not path.exists():
        logger.warning("summary.json not found: %s", path)
        return None
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded baseline summary from %s", path)
    return data


def load_edge_scores(results_dir: Path, variant: str) -> pd.DataFrame | None:
    for candidate in (results_dir / variant, results_dir / "LANL-2015" / variant):
        path = candidate / "edge_scores.csv"
        if path.exists():
            df = pd.read_csv(path)
            logger.info("Loaded edge scores: %d rows from %s", len(df), path)
            return df
    logger.warning("edge_scores.csv not found for variant '%s' under %s", variant, results_dir)
    return None


def load_redteam_events(results_dir: Path) -> pd.DataFrame | None:
    for candidate in (
        results_dir / "redteam" / "redteam_events.csv",
        results_dir / "LANL-2015" / "redteam" / "redteam_events.csv",
    ):
        if candidate.exists():
            df = pd.read_csv(candidate)
            logger.info("Loaded redteam events: %d rows from %s", len(df), candidate)
            return df
    logger.warning("redteam_events.csv not found under %s", results_dir)
    return None


def load_graph_data(results_dir: Path, variant: str) -> tuple | None:
    for candidate in (results_dir / variant, results_dir / "LANL-2015" / variant):
        edges_path = candidate / "graph_edges.csv"
        nodes_path = candidate / "node_features.csv"
        if edges_path.exists():
            edges_df = pd.read_csv(edges_path)
            nodes_df = pd.read_csv(nodes_path) if nodes_path.exists() else None
            logger.info("Loaded graph data for variant '%s': %d edges", variant, len(edges_df))
            return (edges_df, nodes_df)
    logger.warning("graph_edges.csv not found for variant '%s' under %s", variant, results_dir)
    return None
