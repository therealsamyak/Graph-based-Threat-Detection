#!/usr/bin/env python
"""
Standalone baseline testing script for apples-to-apples comparison
with the existing graph-based threat detection results.

Implements:
  - One-Class SVM (unsupervised anomaly detection)
  - SVC (supervised SVM classifier)
  - Isolation Forest (unsupervised anomaly detection)

Uses the SAME methodology as the graph-based pipeline:
  - Same data loading from cached pipeline outputs
  - Same label construction (redteam pairs, valid edge mask)
  - Same rank-percentile transform for non-binary features
  - Same 50/50 stratified split with seed=42
  - Same F1-maximizing threshold optimization
  - Same pair-level metrics (recall, FPR, F1, precision, AUC)

Usage:
    python baseline_test.py                                    # Run on latest results
    python baseline_test.py --run_id 20260520_110758           # Run on specific run_id
    python baseline_test.py --run_id 20260520_110758 --variant combined  # Specific variant
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd
import scipy.stats
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score, f1_score, precision_score, recall_score
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM, SVC

# ── Constants (mirroring src/types.py and src/variants.py) ──────────

BINARY_FEATURES: frozenset[str] = frozenset({
    "is_ntlm",
    "is_network_logon",
    "is_success_auth",
    "is_self_loop",
    "is_user_edge",
    "is_unusual_dst_port",
})

VARIANT_FEATURE_WHITELISTS: dict[str, tuple[str, ...]] = {
    "combined": ("is_ntlm", "dst_in_degree", "is_network_logon", "edge_rarity", "src_out_degree"),
    "auth_only": ("is_ntlm", "src_out_degree", "edge_rarity"),
    "flow_only": ("edge_rarity", "is_unusual_dst_port", "dst_in_degree"),
}

VALID_VARIANTS = {"combined", "auth_only", "flow_only"}

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("baseline_test")


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


# ── Baseline models ──────────────────────────────────────────────────

def run_svm_baseline(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_eval: pd.DataFrame,
    y_eval: np.ndarray,
    eval_edge_pairs: list[tuple[str, str]],
    redteam_pairs: set[tuple[str, str]],
) -> dict:
    """Run SVM baselines (One-Class SVM and SVC) on the eval set.

    Returns dict with one_class_svm and svc results.
    """
    results = {}

    # ── Standardize features ──
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_eval_s = scaler.transform(X_eval)

    # ── One-Class SVM (unsupervised) ──
    logger.info("Training One-Class SVM...")
    oc_svm = OneClassSVM(kernel="rbf", nu=0.1)
    oc_svm.fit(X_train_s)

    # Scores: distance from decision boundary (higher = more anomalous)
    # decision_function returns negative values for anomalies, so we negate
    oc_svm_scores_eval = -oc_svm.decision_function(X_eval_s)

    # Optimize threshold
    best_thresh, best_f1 = optimize_threshold_f1(oc_svm_scores_eval, y_eval.astype(int))

    # Compute pair-level metrics
    oc_svm_metrics = compute_pair_metrics(
        oc_svm_scores_eval, y_eval, eval_edge_pairs, redteam_pairs, best_thresh
    )

    # AUC at edge level
    try:
        if len(np.unique(y_eval)) > 1:
            oc_svm_auc = float(roc_auc_score(y_eval, oc_svm_scores_eval))
        else:
            oc_svm_auc = 0.0
    except ValueError:
        oc_svm_auc = 0.0

    results["one_class_svm"] = {
        "method": "One-Class SVM",
        "kernel": "rbf",
        "nu": 0.1,
        "threshold": best_thresh,
        "f1_at_threshold": best_f1,
        "auc_edge": oc_svm_auc,
        "pair_metrics": oc_svm_metrics,
    }

    # ── SVC (supervised) ──
    logger.info("Training SVC (supervised SVM)...")
    svc = SVC(kernel="rbf", C=1.0, probability=True, random_state=42)
    svc.fit(X_train_s, y_train.astype(int))

    # Scores: probability of positive class
    svc_scores_eval = svc.predict_proba(X_eval_s)[:, 1]

    # Optimize threshold
    best_thresh_svc, best_f1_svc = optimize_threshold_f1(svc_scores_eval, y_eval.astype(int))

    # Compute pair-level metrics
    svc_metrics = compute_pair_metrics(
        svc_scores_eval, y_eval, eval_edge_pairs, redteam_pairs, best_thresh_svc
    )

    # AUC at edge level
    try:
        if len(np.unique(y_eval)) > 1:
            svc_auc = float(roc_auc_score(y_eval, svc_scores_eval))
        else:
            svc_auc = 0.0
    except ValueError:
        svc_auc = 0.0

    results["svc"] = {
        "method": "SVC (supervised)",
        "kernel": "rbf",
        "C": 1.0,
        "threshold": best_thresh_svc,
        "f1_at_threshold": best_f1_svc,
        "auc_edge": svc_auc,
        "pair_metrics": svc_metrics,
    }

    return results


def run_isolation_forest_baseline(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_eval: pd.DataFrame,
    y_eval: np.ndarray,
    eval_edge_pairs: list[tuple[str, str]],
    redteam_pairs: set[tuple[str, str]],
) -> dict:
    """Run Isolation Forest baseline on the eval set.

    Returns dict with iforest results.
    """
    logger.info("Training Isolation Forest...")
    iforest = IsolationForest(
        contamination="auto",
        n_estimators=100,
        random_state=42,
    )
    iforest.fit(X_train)

    # Scores: negative of anomaly score (higher = more anomalous)
    # score_samples returns negative values for anomalies, so we negate
    iforest_scores_eval = -iforest.score_samples(X_eval)

    # Optimize threshold
    best_thresh, best_f1 = optimize_threshold_f1(iforest_scores_eval, y_eval.astype(int))

    # Compute pair-level metrics
    iforest_metrics = compute_pair_metrics(
        iforest_scores_eval, y_eval, eval_edge_pairs, redteam_pairs, best_thresh
    )

    # AUC at edge level
    try:
        if len(np.unique(y_eval)) > 1:
            iforest_auc = float(roc_auc_score(y_eval, iforest_scores_eval))
        else:
            iforest_auc = 0.0
    except ValueError:
        iforest_auc = 0.0

    results = {
        "method": "Isolation Forest",
        "n_estimators": 100,
        "contamination": "auto",
        "random_state": 42,
        "threshold": best_thresh,
        "f1_at_threshold": best_f1,
        "auc_edge": iforest_auc,
        "pair_metrics": iforest_metrics,
    }

    return results


# ── Load graph-based results for comparison ──────────────────────────

def load_graph_based_results(run_dir: Path, variant: str) -> dict | None:
    """Load existing graph-based detection results from the same run_id.

    Tries to find edge_scores.csv and compute metrics from the graph-based pipeline.
    """
    try:
        variant_dir = _find_variant_dir(run_dir, variant)
    except FileNotFoundError:
        return None

    edge_scores_path = variant_dir / "edge_scores.csv"
    graph_edges_path = variant_dir / "graph_edges.csv"

    try:
        redteam_pairs_path = _find_redteam_pairs(run_dir)
    except FileNotFoundError:
        return None

    if not edge_scores_path.exists():
        logger.warning(f"Graph-based edge_scores.csv not found: {edge_scores_path}")
        return None

    try:
        edge_scores_df = pd.read_csv(edge_scores_path)
        graph_edges_df = pd.read_csv(graph_edges_path)

        with open(redteam_pairs_path) as f:
            redteam_pairs = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}

        edge_pairs = list(
            zip(
                graph_edges_df["src"].astype(str).values,
                graph_edges_df["dst"].astype(str).values,
            )
        )

        # Get scores
        if "score" in edge_scores_df.columns:
            scores = edge_scores_df["score"].values
        elif "edge_score" in edge_scores_df.columns:
            scores = edge_scores_df["edge_score"].values
        else:
            # Try first numeric column after src/dst
            numeric_cols = edge_scores_df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                scores = edge_scores_df[numeric_cols[0]].values
            else:
                logger.warning(f"No score column found in {edge_scores_path}")
                return None

        # Valid mask
        is_self_loop = (
            edge_scores_df["is_self_loop"].values
            if "is_self_loop" in edge_scores_df.columns
            else np.zeros(len(edge_scores_df))
        )
        is_user_edge = (
            edge_scores_df["is_user_edge"].values
            if "is_user_edge" in edge_scores_df.columns
            else np.zeros(len(edge_scores_df))
        )
        valid_mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

        labels = np.fromiter(
            (pair in redteam_pairs for pair in edge_pairs),
            dtype=np.float64,
            count=len(edge_pairs),
        )

        scores_valid = scores[valid_mask]
        labels_valid = labels[valid_mask]
        valid_edge_pairs = [edge_pairs[i] for i in range(len(edge_pairs)) if valid_mask[i]]

        # Optimize threshold
        best_thresh, best_f1 = optimize_threshold_f1(scores_valid, labels_valid.astype(int))

        # Compute pair-level metrics
        graph_metrics = compute_pair_metrics(
            scores_valid, labels_valid, valid_edge_pairs, redteam_pairs, best_thresh
        )

        # AUC
        try:
            if len(np.unique(labels_valid)) > 1:
                graph_auc = float(roc_auc_score(labels_valid, scores_valid))
            else:
                graph_auc = 0.0
        except ValueError:
            graph_auc = 0.0

        return {
            "method": "Graph-based (weighted sum + path boost)",
            "threshold": best_thresh,
            "f1_at_threshold": best_f1,
            "auc_edge": graph_auc,
            "pair_metrics": graph_metrics,
        }

    except Exception as e:
        logger.warning(f"Failed to load graph-based results for {variant}: {e}")
        return None


# ── Main evaluation pipeline ─────────────────────────────────────────

def evaluate_variant(
    run_dir: Path,
    variant: str,
    output_dir: Path,
) -> dict:
    """Run all baselines on a single variant and save results.

    Returns dict with per-method results.
    """
    logger.info(f"{'=' * 60}")
    logger.info(f"Evaluating variant: {variant}")
    logger.info(f"{'=' * 60}")

    variant_output_dir = output_dir / variant
    variant_output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ──
    edge_features_df, graph_edges_df, edge_pairs, redteam_pairs = load_variant_data(
        run_dir, variant
    )

    # ── Prepare features and labels ──
    X_valid, labels_valid, valid_mask, valid_edge_pairs = prepare_features_and_labels(
        edge_features_df, graph_edges_df, edge_pairs, redteam_pairs, variant
    )

    # ── Stratified split (50/50, seed=42) ──
    train_idx, eval_idx = train_test_split(
        np.arange(len(X_valid)),
        test_size=0.5,
        stratify=labels_valid,
        random_state=42,
    )

    X_train = X_valid.iloc[train_idx].reset_index(drop=True)
    y_train = labels_valid[train_idx]
    X_eval = X_valid.iloc[eval_idx].reset_index(drop=True)
    y_eval = labels_valid[eval_idx]
    eval_edge_pairs = [valid_edge_pairs[i] for i in eval_idx]

    logger.info(
        f"Split: {len(X_train)} train edges ({int(y_train.sum())} positive), "
        f"{len(X_eval)} eval edges ({int(y_eval.sum())} positive)"
    )

    # ── Run baselines ──
    all_results = {}

    # SVM baselines
    svm_results = run_svm_baseline(
        X_train, y_train, X_eval, y_eval, eval_edge_pairs, redteam_pairs
    )
    all_results.update(svm_results)

    # Save SVM detailed results
    for method_key in ["one_class_svm", "svc"]:
        if method_key in svm_results:
            save_path = variant_output_dir / f"{method_key.replace('_', '_')}_results.json"
            with open(save_path, "w") as f:
                json.dump(svm_results[method_key], f, indent=2, default=str)
            logger.info(f"Saved {save_path}")

    # Isolation Forest baseline
    iforest_results = run_isolation_forest_baseline(
        X_train, y_train, X_eval, y_eval, eval_edge_pairs, redteam_pairs
    )
    all_results["isolation_forest"] = iforest_results

    # Save IF results
    with open(variant_output_dir / "iforest_results.json", "w") as f:
        json.dump(iforest_results, f, indent=2, default=str)
    logger.info(f"Saved {variant_output_dir / 'iforest_results.json'}")

    # ── Save edge scores for comparison ──
    # Generate scores for all eval edges from each method
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_eval_s = scaler.transform(X_eval)

    # One-Class SVM scores
    oc_svm = OneClassSVM(kernel="rbf", nu=0.1)
    oc_svm.fit(X_train_s)
    oc_svm_scores = -oc_svm.decision_function(X_eval_s)

    # SVC scores
    svc = SVC(kernel="rbf", C=1.0, probability=True, random_state=42)
    svc.fit(X_train_s, y_train.astype(int))
    svc_scores = svc.predict_proba(X_eval_s)[:, 1]

    # Isolation Forest scores
    iforest = IsolationForest(contamination="auto", n_estimators=100, random_state=42)
    iforest.fit(X_train)
    iforest_scores = -iforest.score_samples(X_eval)

    # Save edge scores
    scores_df = pd.DataFrame(
        {
            "src": [p[0] for p in eval_edge_pairs],
            "dst": [p[1] for p in eval_edge_pairs],
            "label": y_eval.astype(int),
            "one_class_svm_score": oc_svm_scores,
            "svc_score": svc_scores,
            "isolation_forest_score": iforest_scores,
        }
    )
    scores_df.to_csv(variant_output_dir / "edge_scores.csv", index=False)
    logger.info(f"Saved {variant_output_dir / 'edge_scores.csv'}")

    return all_results


def build_comparison_table(
    per_variant_results: dict[str, dict],
    graph_results: dict[str, dict | None],
) -> str:
    """Build a markdown comparison table."""
    lines = [
        "# Baseline Comparison: Graph-based vs SVM vs Isolation Forest",
        "",
        "## Per-Variant Results",
        "",
    ]

    for variant in ["combined", "auth_only", "flow_only"]:
        if variant not in per_variant_results:
            continue

        lines.append(f"### {variant}")
        lines.append("")
        lines.append(
            "| Method | Recall | FPR | F1 | Precision | AUC |"
        )
        lines.append(
            "|--------|--------|-----|----|-----------|-----|"
        )

        # Graph-based
        graph = graph_results.get(variant)
        if graph:
            pm = graph.get("pair_metrics", {})
            lines.append(
                f"| Graph-based | {pm.get('recall', 'N/A'):.4f} | "
                f"{pm.get('fpr', 'N/A'):.4f} | {pm.get('f1', 'N/A'):.4f} | "
                f"{pm.get('precision', 'N/A'):.4f} | {graph.get('auc_edge', 'N/A'):.4f} |"
            )
        else:
            lines.append("| Graph-based | N/A | N/A | N/A | N/A | N/A |")

        # Baselines
        variant_results = per_variant_results[variant]
        for method_key, method_name in [
            ("svc", "SVC (supervised)"),
            ("one_class_svm", "One-Class SVM"),
            ("isolation_forest", "Isolation Forest"),
        ]:
            if method_key in variant_results:
                pm = variant_results[method_key].get("pair_metrics", {})
                lines.append(
                    f"| {method_name} | {pm.get('recall', 'N/A'):.4f} | "
                    f"{pm.get('fpr', 'N/A'):.4f} | {pm.get('f1', 'N/A'):.4f} | "
                    f"{pm.get('precision', 'N/A'):.4f} | "
                    f"{variant_results[method_key].get('auc_edge', 'N/A'):.4f} |"
                )
            else:
                lines.append(f"| {method_name} | N/A | N/A | N/A | N/A | N/A |")

        lines.append("")

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Baseline testing: SVM and Isolation Forest for threat detection comparison"
    )
    parser.add_argument(
        "--run_id",
        type=str,
        default=None,
        help="Specific run_id to evaluate (e.g., 20260520_110758). Defaults to latest.",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        choices=["combined", "auth_only", "flow_only"],
        help="Evaluate specific variant. Default: evaluate all found variants.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory to search for cached runs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("baseline_results"),
        help="Output directory for baseline results.",
    )

    args = parser.parse_args()

    # ── Determine run directory ──
    if args.run_id:
        run_dir_path = args.results_dir / args.run_id
        if not run_dir_path.exists():
            raise FileNotFoundError(f"Run directory not found: {run_dir_path}")
    else:
        run_dir_path = find_latest_run(args.results_dir)
        logger.info(f"Using latest run: {run_dir_path.name}")

    # ── Determine variants to evaluate ──
    variants_to_eval = []
    for v in VALID_VARIANTS:
        try:
            _find_variant_dir(run_dir_path, v)
            variants_to_eval.append(v)
        except FileNotFoundError:
            pass

    if args.variant:
        if args.variant not in variants_to_eval:
            raise FileNotFoundError(
                f"Variant '{args.variant}' not found in run {run_dir_path.name}. "
                f"Available: {variants_to_eval}"
            )
        variants_to_eval = [args.variant]

    if not variants_to_eval:
        raise FileNotFoundError(
            f"No valid variants found in {run_dir_path}. "
            f"Ensure the directory contains variant subdirectories with edge_features.csv."
        )

    logger.info(f"Evaluating variants: {variants_to_eval}")

    # ── Create output directory ──
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_dir / timestamp
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {output_dir}")

    # ── Evaluate each variant ──
    per_variant_results: dict[str, dict] = {}
    graph_results: dict[str, dict | None] = {}

    for variant in variants_to_eval:
        start_time = time.time()

        # Run baselines
        variant_results = evaluate_variant(run_dir_path, variant, output_dir)
        per_variant_results[variant] = variant_results

        # Load graph-based results for comparison
        graph = load_graph_based_results(run_dir_path, variant)
        graph_results[variant] = graph

        elapsed = time.time() - start_time
        logger.info(f"Completed {variant} in {elapsed:.1f}s")

    # ── Build comparison table ──
    comparison_md = build_comparison_table(per_variant_results, graph_results)
    (output_dir / "comparison_table.md").write_text(comparison_md)
    logger.info(f"Saved {output_dir / 'comparison_table.md'}")

    # ── Build summary ──
    summary = {
        "timestamp": timestamp,
        "run_id": run_dir_path.name,
        "variants_evaluated": variants_to_eval,
        "methods": ["One-Class SVM", "SVC (supervised)", "Isolation Forest"],
        "per_variant_summary": {},
    }

    for variant in variants_to_eval:
        variant_summary = {}
        for method_key in ["one_class_svm", "svc", "isolation_forest"]:
            if method_key in per_variant_results.get(variant, {}):
                m = per_variant_results[variant][method_key]
                pm = m.get("pair_metrics", {})
                variant_summary[method_key] = {
                    "recall": pm.get("recall"),
                    "fpr": pm.get("fpr"),
                    "f1": pm.get("f1"),
                    "precision": pm.get("precision"),
                    "auc": m.get("auc_edge"),
                }

        # Add graph-based if available
        if graph_results.get(variant):
            g = graph_results[variant]
            pm = g.get("pair_metrics", {})
            variant_summary["graph_based"] = {
                "recall": pm.get("recall"),
                "fpr": pm.get("fpr"),
                "f1": pm.get("f1"),
                "precision": pm.get("precision"),
                "auc": g.get("auc_edge"),
            }

        summary["per_variant_summary"][variant] = variant_summary

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'summary.json'}")

    # ── Save per-variant detailed results ──
    with open(output_dir / "per_variant_results.json", "w") as f:
        json.dump(per_variant_results, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'per_variant_results.json'}")

    # ── Print summary ──
    print(f"\n{'=' * 70}")
    print(f"Baseline testing complete: {output_dir}")
    print(f"Run ID: {run_dir_path.name}")
    print(f"{'=' * 70}")
    print(comparison_md)


if __name__ == "__main__":
    main()
