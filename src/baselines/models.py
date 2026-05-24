"""Baseline model training and evaluation (One-Class SVM, Isolation Forest)."""

from __future__ import annotations

import logging
from typing import TypeAlias

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.baselines.data import Pair, evaluate_scores

logger = logging.getLogger(__name__)

BaselineResult: TypeAlias = dict[str, object]


def _result_with_scores(
    method: str,
    model_params: dict[str, object],
    scores: np.ndarray,
    eval_edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
) -> BaselineResult:
    threshold, f1_at_threshold, pair_metrics = evaluate_scores(
        scores,
        eval_edge_pairs,
        redteam_pairs,
    )
    return {
        "method": method,
        **model_params,
        "threshold": threshold,
        "f1_at_threshold": f1_at_threshold,
        "auc_edge": float(pair_metrics["auc"]),
        "pair_metrics": pair_metrics,
        "eval_scores": scores,
    }


def run_one_class_svm(
    X_train: pd.DataFrame,
    X_eval: pd.DataFrame,
    eval_edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
) -> BaselineResult:
    """Run One-Class SVM baseline on the eval set."""
    scaler = StandardScaler().fit(X_train)
    X_train_s = scaler.transform(X_train)
    X_eval_s = scaler.transform(X_eval)

    logger.info("Training One-Class SVM...")
    oc_svm = OneClassSVM(kernel="rbf", nu=0.1)
    oc_svm.fit(X_train_s)

    scores = -oc_svm.decision_function(X_eval_s)
    return _result_with_scores(
        "One-Class SVM",
        {"kernel": "rbf", "nu": 0.1},
        scores,
        eval_edge_pairs,
        redteam_pairs,
    )


def run_isolation_forest_baseline(
    X_train: pd.DataFrame,
    X_eval: pd.DataFrame,
    eval_edge_pairs: list[Pair],
    redteam_pairs: set[Pair],
) -> BaselineResult:
    """Run Isolation Forest baseline on the eval set."""
    logger.info("Training Isolation Forest...")
    iforest = IsolationForest(
        contamination="auto",
        n_estimators=100,
        random_state=42,
    )
    iforest.fit(X_train)

    scores = -iforest.score_samples(X_eval)
    return _result_with_scores(
        "Isolation Forest",
        {"n_estimators": 100, "contamination": "auto", "random_state": 42},
        scores,
        eval_edge_pairs,
        redteam_pairs,
    )
