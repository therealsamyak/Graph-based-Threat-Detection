"""Data loading, feature preparation, and score evaluation for baselines."""

from __future__ import annotations

import json
import logging
from numbers import Real
from pathlib import Path
from typing import TypeAlias

import numpy as np
import pandas as pd
import scipy.stats

from src.csv_split import csv_exists, load_csv_merged
from src.detection import compute_pair_metrics as compute_detection_pair_metrics
from src.detection import optimize_threshold
from src.types import BINARY_FEATURES, DetectionParams
from src.variants import get_variant

logger = logging.getLogger(__name__)

Pair: TypeAlias = tuple[str, str]
PairMetrics: TypeAlias = dict[str, float | int]

VALID_EDGE_COLUMNS = ("is_self_loop", "is_user_edge")


# ── Utility functions ────────────────────────────────────────────────


def rank_pct(x: np.ndarray) -> np.ndarray:
    """Transform to percentile ranks within the column."""
    values = np.asarray(x, dtype=float)
    if len(values) == 0:
        return values
    rank = scipy.stats.rankdata(values, method="average")
    return rank / len(rank)


def labels_for_pairs(edge_pairs: list[Pair], redteam_pairs: set[Pair]) -> np.ndarray:
    """Build binary edge labels from red-team src/dst pairs."""
    return np.fromiter(
        (pair in redteam_pairs for pair in edge_pairs),
        dtype=np.float64,
        count=len(edge_pairs),
    )


def valid_edge_mask(edge_features_df: pd.DataFrame) -> np.ndarray:
    """Return mask for non-self-loop, non-user edges.

    These columns are part of the cached edge-feature schema. Missing columns are
    a schema error; silently treating them as zero corrupts metrics.
    """
    missing = [col for col in VALID_EDGE_COLUMNS if col not in edge_features_df.columns]
    if missing:
        raise KeyError(f"Missing required edge-feature columns: {missing}")

    return (
        (edge_features_df["is_self_loop"].to_numpy() == 0.0)
        & (edge_features_df["is_user_edge"].to_numpy() == 0.0)
    )


def _metric_as_float(metrics: dict[str, object], key: str) -> float:
    value = metrics[key]
    if not isinstance(value, Real):
        raise TypeError(f"Metric '{key}' is not numeric: {type(value).__name__}")
    return float(value)


def _metric_as_set(metrics: dict[str, object], key: str) -> set[object]:
    value = metrics[key]
    if not isinstance(value, set):
        raise TypeError(f"Metric '{key}' is not a set: {type(value).__name__}")
    return value


def detection_params_for_scores(
    scores: np.ndarray,
    edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
) -> DetectionParams:
    """Adapt baseline score arrays to the canonical detection interface."""
    if len(scores) != len(edge_pairs):
        raise ValueError(
            f"Score count ({len(scores)}) does not match edge-pair count ({len(edge_pairs)})"
        )

    edge_pair_names = tuple(edge_pairs)
    all_graph_edges = frozenset(edge_pair_names)
    positive_pairs_in_graph = frozenset(redteam_pairs & set(all_graph_edges))

    return DetectionParams(
        edge_scores=pd.Series(np.asarray(scores, dtype=float)),
        mask_valid=pd.Series(np.ones(len(edge_pair_names), dtype=bool)),
        edge_pair_names=edge_pair_names,
        positive_pairs_in_graph=positive_pairs_in_graph,
        all_positive_pairs=frozenset(redteam_pairs),
        all_graph_edges=all_graph_edges,
    )


def summarize_detection_metrics(metrics: dict[str, object], redteam_pairs: set[Pair]) -> PairMetrics:
    """Keep the baseline JSON schema while reusing canonical detection metrics."""
    anomalous_pairs = _metric_as_set(metrics, "anomalous_pairs")
    detected_pairs = _metric_as_set(metrics, "detected_pairs")
    return {
        "recall": _metric_as_float(metrics, "recall"),
        "fpr": _metric_as_float(metrics, "fpr"),
        "f1": _metric_as_float(metrics, "f1"),
        "precision": _metric_as_float(metrics, "precision"),
        "auc": _metric_as_float(metrics, "auc"),
        "num_anomalous_pairs": len(anomalous_pairs),
        "num_detected_pairs": len(detected_pairs),
        "num_redteam_pairs": len(redteam_pairs),
    }


def evaluate_scores(
    scores: np.ndarray,
    edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
) -> tuple[float, float, PairMetrics]:
    """Optimize threshold and compute pair metrics via canonical detection code."""
    params = detection_params_for_scores(scores, edge_pairs, redteam_pairs)
    threshold, _ = optimize_threshold(params)
    raw_metrics = compute_detection_pair_metrics(params, threshold)
    metrics = summarize_detection_metrics(raw_metrics, redteam_pairs)
    return threshold, float(metrics["f1"]), metrics


# ── Data loading ─────────────────────────────────────────────────────


def find_latest_run(results_dir: Path) -> Path:
    """Find the latest run directory under results/."""
    run_dirs = sorted(
        [d for d in results_dir.iterdir() if d.is_dir() and d.name != "pending"],
        key=lambda d: d.name,
        reverse=True,
    )
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {results_dir}")
    return run_dirs[0]


def find_variant_dir(run_dir: Path, variant: str) -> Path:
    """Find a variant directory in direct or nested dataset run layouts."""
    direct = run_dir / variant
    if direct.is_dir() and csv_exists(direct / "edge_features.csv"):
        return direct

    for subdir in run_dir.iterdir():
        if subdir.is_dir():
            nested = subdir / variant
            if nested.is_dir() and csv_exists(nested / "edge_features.csv"):
                return nested

    raise FileNotFoundError(
        f"Variant directory not found for '{variant}' under {run_dir}. "
        f"Tried {direct} and nested patterns."
    )


def find_redteam_pairs(run_dir: Path) -> Path:
    """Find redteam_pairs.json in direct, nested, or parent run layouts."""
    candidate = run_dir / "redteam" / "redteam_pairs.json"
    if candidate.exists():
        return candidate

    for subdir in run_dir.iterdir():
        if subdir.is_dir():
            candidate = subdir / "redteam" / "redteam_pairs.json"
            if candidate.exists():
                return candidate

    candidate = run_dir.parent / "redteam" / "redteam_pairs.json"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"redteam_pairs.json not found under {run_dir} or its parent."
    )


def load_variant_data(
    run_dir: Path,
    variant: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[Pair], set[Pair]]:
    """Load edge_features.csv, graph_edges.csv, and redteam_pairs.json for a variant."""
    variant_dir = find_variant_dir(run_dir, variant)
    redteam_pairs_path = find_redteam_pairs(run_dir)

    edge_features_path = variant_dir / "edge_features.csv"
    graph_edges_path = variant_dir / "graph_edges.csv"

    if not csv_exists(edge_features_path):
        raise FileNotFoundError(f"Required file not found: {edge_features_path}")
    if not graph_edges_path.exists():
        raise FileNotFoundError(f"Required file not found: {graph_edges_path}")
    if not redteam_pairs_path.exists():
        raise FileNotFoundError(f"Required file not found: {redteam_pairs_path}")

    edge_features_df = load_csv_merged(edge_features_path)
    graph_edges_df = pd.read_csv(graph_edges_path)

    with open(redteam_pairs_path) as f:
        redteam_pairs = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}

    edge_pairs = list(
        zip(
            graph_edges_df["src"].astype(str).to_numpy(),
            graph_edges_df["dst"].astype(str).to_numpy(),
        )
    )

    logger.info(
        f"Loaded {variant}: {len(edge_features_df)} edges, "
        f"{len(redteam_pairs)} redteam pairs"
    )

    return edge_features_df, graph_edges_df, edge_pairs, redteam_pairs


# ── Feature processing ───────────────────────────────────────────────


def load_feature_whitelist(variant_dir: Path, variant: str) -> tuple[str, ...]:
    """Load feature whitelist from pipeline output, fall back to variant descriptor."""
    wl_path = variant_dir / "feature_whitelist.json"
    if wl_path.exists():
        with open(wl_path) as f:
            data = json.load(f)
        features = data.get("features", [])
        if features:
            logger.info(f"Using pipeline feature whitelist for {variant}: {features}")
            return tuple(features)
    fallback = get_variant(variant).feature_whitelist
    logger.info(f"No pipeline whitelist found for {variant}, using descriptor: {fallback}")
    return fallback


def prepare_features_and_labels(
    edge_features_df: pd.DataFrame,
    edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
    variant: str,
    feature_whitelist: tuple[str, ...] | None = None,
) -> tuple[pd.DataFrame, np.ndarray, list[Pair]]:
    """Prepare feature matrix and labels with the canonical variant whitelist."""
    if feature_whitelist is None:
        feature_whitelist = get_variant(variant).feature_whitelist

    available_features = set(edge_features_df.columns)
    features_to_use = [f for f in feature_whitelist if f in available_features]
    missing = [f for f in feature_whitelist if f not in available_features]
    if missing:
        logger.warning(f"Features not available for {variant}: {missing}")

    if not features_to_use:
        raise ValueError(f"No features available for variant {variant}")

    valid_mask = valid_edge_mask(edge_features_df)
    labels = labels_for_pairs(edge_pairs, redteam_pairs)

    X = edge_features_df[features_to_use].copy()
    for col in features_to_use:
        if col not in BINARY_FEATURES:
            X[col] = rank_pct(np.asarray(X[col], dtype=float))

    X_valid = X.loc[valid_mask].reset_index(drop=True)
    labels_valid = labels[valid_mask]
    valid_edge_pairs = [edge_pairs[i] for i in range(len(edge_pairs)) if valid_mask[i]]

    X_valid = X_valid.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    logger.info(
        f"Prepared features for {variant}: {X_valid.shape[0]} valid edges, "
        f"{X_valid.shape[1]} features, {int(labels_valid.sum())} positive"
    )

    return X_valid, labels_valid, valid_edge_pairs
