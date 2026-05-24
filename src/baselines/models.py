"""Baseline model training and evaluation (One-Class SVM, Isolation Forest)."""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.baselines.data import compute_pair_metrics, optimize_threshold_f1

logger = logging.getLogger(__name__)


def run_one_class_svm(
    X_train: pd.DataFrame,
    y_train: np.ndarray,
    X_eval: pd.DataFrame,
    y_eval: np.ndarray,
    eval_edge_pairs: list[tuple[str, str]],
    redteam_pairs: set[tuple[str, str]],
) -> dict:
    """Run One-Class SVM baseline on the eval set.

    Returns dict with method results (includes eval_scores numpy array).
    """
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

    return {
        "method": "One-Class SVM",
        "kernel": "rbf",
        "nu": 0.1,
        "threshold": best_thresh,
        "f1_at_threshold": best_f1,
        "auc_edge": oc_svm_auc,
        "pair_metrics": oc_svm_metrics,
        "eval_scores": oc_svm_scores_eval,
    }


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
        "eval_scores": iforest_scores_eval,
    }

    return results
