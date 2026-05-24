"""Data loading, feature preparation, and metric computation for baselines."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats
from sklearn.metrics import f1_score, roc_auc_score

from src.baselines.types import BINARY_FEATURES, VARIANT_FEATURE_WHITELISTS

logger = logging.getLogger(__name__)


# ── Utility functions ────────────────────────────────────────────────


def rank_pct(x: np.ndarray) -> np.ndarray:
    """Transform to percentile ranks within the column."""
    rank = scipy.stats.rankdata(x, method="average")
    return rank / len(rank)


def optimize_threshold_f1(
    scores: np.ndarray,
    labels: np.ndarray,
    percentiles: list[float] | None = None,
) -> tuple[float, float]:
    """Auto-optimize threshold by sweeping percentiles to maximize F1.

    Returns (best_threshold, best_f1).
    """
    if percentiles is None:
        percentiles = [90, 95, 97, 99, 99.5, 99.9]

    best_f1: float = -1.0
    best_thresh: float = float(scores.min())

    for p in percentiles:
        thresh = float(np.percentile(scores, p))
        preds = (scores >= thresh).astype(int)
        f1 = f1_score(labels, preds, zero_division=0)
        if f1 > best_f1:
            best_f1 = f1
            best_thresh = thresh

    return best_thresh, best_f1


def compute_pair_metrics(
    scores: np.ndarray,
    labels: np.ndarray,
    edge_pairs: list[tuple[str, str]],
    redteam_pairs: set[tuple[str, str]],
    threshold: float,
) -> dict:
    """Compute recall, FPR, F1, precision, AUC at the pair level.

    For each redteam pair, check if ANY edge between that src-dst pair exceeds threshold.
    """
    # Build mapping from pair to max score
    pair_max_score: dict[tuple[str, str], float] = {}
    for i, pair in enumerate(edge_pairs):
        if pair not in pair_max_score:
            pair_max_score[pair] = scores[i]
        else:
            pair_max_score[pair] = max(pair_max_score[pair], scores[i])

    # All unique pairs in the graph
    all_graph_pairs = set(edge_pairs)

    # Pairs that exceed threshold
    anomalous_pairs = {pair for pair, score in pair_max_score.items() if score >= threshold}

    # Detected redteam pairs
    detected_pairs = anomalous_pairs & redteam_pairs

    # Recall: fraction of redteam pairs detected
    recall = len(detected_pairs) / len(redteam_pairs) if redteam_pairs else 0.0

    # FPR: false positives / (false positives + true negatives)
    false_positives = len(anomalous_pairs - redteam_pairs)
    true_negatives = len(all_graph_pairs - anomalous_pairs - redteam_pairs)
    fpr = false_positives / max(false_positives + true_negatives, 1)

    # Precision
    precision = len(detected_pairs) / max(len(anomalous_pairs), 1)

    # F1
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

    # AUC: use pair-level scores and labels
    unique_pairs = sorted(pair_max_score.keys())
    pair_scores = np.array([pair_max_score[p] for p in unique_pairs])
    pair_labels = np.array([1.0 if p in redteam_pairs else 0.0 for p in unique_pairs])

    try:
        if len(np.unique(pair_labels)) > 1:
            auc = float(roc_auc_score(pair_labels, pair_scores))
        else:
            auc = 0.0
            logger.warning("Only one class present in pairs — AUC undefined")
    except ValueError:
        auc = 0.0
        logger.warning("AUC computation failed")

    return {
        "recall": recall,
        "fpr": fpr,
        "f1": f1,
        "precision": precision,
        "auc": auc,
        "num_anomalous_pairs": len(anomalous_pairs),
        "num_detected_pairs": len(detected_pairs),
        "num_redteam_pairs": len(redteam_pairs),
    }


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


def _find_variant_dir(run_dir: Path, variant: str) -> Path:
    """Find the variant directory, handling nested dataset structures.

    Handles both:
      - run_dir/variant/
      - run_dir/*/variant/  (e.g., run_dir/LANL-2015/variant/)
    """
    # Try direct path: run_dir/variant/
    direct = run_dir / variant
    if direct.is_dir() and (direct / "edge_features.csv").exists():
        return direct

    # Try nested: run_dir/*/variant/
    for subdir in run_dir.iterdir():
        if subdir.is_dir():
            nested = subdir / variant
            if nested.is_dir() and (nested / "edge_features.csv").exists():
                return nested

    raise FileNotFoundError(
        f"Variant directory not found for '{variant}' under {run_dir}. "
        f"Tried {direct} and nested patterns."
    )


def _find_redteam_pairs(run_dir: Path) -> Path:
    """Find redteam_pairs.json, handling nested dataset structures."""
    # Try run_dir/redteam/redteam_pairs.json
    candidate = run_dir / "redteam" / "redteam_pairs.json"
    if candidate.exists():
        return candidate

    # Try run_dir/*/redteam/redteam_pairs.json
    for subdir in run_dir.iterdir():
        if subdir.is_dir():
            candidate = subdir / "redteam" / "redteam_pairs.json"
            if candidate.exists():
                return candidate

    # Try parent level
    candidate = run_dir.parent / "redteam" / "redteam_pairs.json"
    if candidate.exists():
        return candidate

    raise FileNotFoundError(
        f"redteam_pairs.json not found under {run_dir} or its parent."
    )


def load_variant_data(
    run_dir: Path,
    variant: str,
) -> tuple[pd.DataFrame, pd.DataFrame, list[tuple[str, str]], set[tuple[str, str]]]:
    """Load edge_features.csv, graph_edges.csv, and redteam_pairs.json for a variant.

    Returns:
        edge_features_df: Full feature matrix (all edges)
        graph_edges_df: Edge metadata (src, dst, is_self_loop, is_user_edge)
        edge_pairs: List of (src, dst) tuples for each edge row
        redteam_pairs: Set of (src, dst) ground truth pairs
    """
    variant_dir = _find_variant_dir(run_dir, variant)
    redteam_pairs_path = _find_redteam_pairs(run_dir)

    edge_features_path = variant_dir / "edge_features.csv"
    graph_edges_path = variant_dir / "graph_edges.csv"

    for path in (edge_features_path, graph_edges_path, redteam_pairs_path):
        if not path.exists():
            raise FileNotFoundError(f"Required file not found: {path}")

    edge_features_df = pd.read_csv(edge_features_path)
    graph_edges_df = pd.read_csv(graph_edges_path)

    with open(redteam_pairs_path) as f:
        redteam_pairs = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}

    edge_pairs = list(
        zip(
            graph_edges_df["src"].astype(str).values,
            graph_edges_df["dst"].astype(str).values,
        )
    )

    logger.info(
        f"Loaded {variant}: {len(edge_features_df)} edges, "
        f"{len(redteam_pairs)} redteam pairs"
    )

    return edge_features_df, graph_edges_df, edge_pairs, redteam_pairs


# ── Feature processing ───────────────────────────────────────────────


def prepare_features_and_labels(
    edge_features_df: pd.DataFrame,
    graph_edges_df: pd.DataFrame,
    edge_pairs: list[tuple[str, str]],
    redteam_pairs: set[tuple[str, str]],
    variant: str,
) -> tuple[pd.DataFrame, np.ndarray, np.ndarray, list[tuple[str, str]]]:
    """Prepare feature matrix and labels, applying valid edge mask and rank-percentile transform.

    Returns:
        X_transformed: Transformed feature matrix (valid edges only)
        labels: Binary labels (valid edges only)
        valid_mask: Boolean mask for valid edges
        valid_edge_pairs: Edge pairs for valid edges
    """
    # Get feature whitelist for this variant
    feature_whitelist = VARIANT_FEATURE_WHITELISTS.get(variant)
    if feature_whitelist is None:
        raise ValueError(f"Unknown variant: {variant}")

    # Check which features are available
    available_features = set(edge_features_df.columns)
    features_to_use = [f for f in feature_whitelist if f in available_features]
    missing = [f for f in feature_whitelist if f not in available_features]
    if missing:
        logger.warning(f"Features not available for {variant}: {missing}")

    if not features_to_use:
        raise ValueError(f"No features available for variant {variant}")

    # Build valid edge mask: exclude self-loops and user edges
    is_self_loop = (
        edge_features_df["is_self_loop"].values
        if "is_self_loop" in edge_features_df.columns
        else np.zeros(len(edge_features_df))
    )
    is_user_edge = (
        edge_features_df["is_user_edge"].values
        if "is_user_edge" in edge_features_df.columns
        else np.zeros(len(edge_features_df))
    )
    valid_mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

    # Create binary labels: 1 if (src, dst) pair is in redteam_pairs
    labels = np.fromiter(
        (pair in redteam_pairs for pair in edge_pairs),
        dtype=np.float64,
        count=len(edge_pairs),
    )

    # Extract feature columns
    X = edge_features_df[features_to_use].copy()

    # Apply rank-percentile transform to non-binary features
    for col in features_to_use:
        if col not in BINARY_FEATURES:
            X[col] = rank_pct(X[col].values)

    # Filter to valid edges
    X_valid = X.loc[valid_mask].reset_index(drop=True)
    labels_valid = labels[valid_mask]
    valid_edge_pairs = [edge_pairs[i] for i in range(len(edge_pairs)) if valid_mask[i]]

    # Replace inf/nan
    X_valid = X_valid.replace([np.inf, -np.inf], 0.0).fillna(0.0)

    logger.info(
        f"Prepared features for {variant}: {X_valid.shape[0]} valid edges, "
        f"{X_valid.shape[1]} features, {int(labels_valid.sum())} positive"
    )

    return X_valid, labels_valid, valid_mask, valid_edge_pairs
