"""Shared baseline runners: OneClassSVM and IsolationForest."""

from __future__ import annotations

import logging
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

logger = logging.getLogger(__name__)

SCORING_FEATURE_COLUMNS = [
    "edge_rarity",
    "is_ntlm",
    "is_network_logon",
    "is_unusual_dst_port",
    "protocol_rarity",
]


def _prepare_train_test(
    features: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    """Split features into train (normal only) and test (all), scaled. Returns None if invalid."""
    normal_mask = labels == 0
    if normal_mask.sum() == 0:
        return None
    scaler = StandardScaler()
    X_train = scaler.fit_transform(features[normal_mask])
    X_test = scaler.transform(features)
    return X_train, X_test, labels


def _run_svm(args: tuple) -> dict:
    X_train, X_test, y_test, svm_cfg = args
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = OneClassSVM(
            kernel=svm_cfg.get("kernel", "rbf"),
            gamma=svm_cfg.get("gamma", "scale"),
            nu=svm_cfg.get("nu", 0.1),
        )
        model.fit(X_train)
    preds = model.predict(X_test)
    y_pred = (preds == -1).astype(int)
    decision = model.decision_function(X_test)
    auc = roc_auc_score(y_test, -decision) if len(np.unique(y_test)) > 1 else 0.0
    f1 = f1_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    prec = precision_score(y_test, y_pred, zero_division=0)
    tn = np.sum((y_test == 0) & (y_pred == 0))
    fp = np.sum((y_test == 0) & (y_pred == 1))
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "method": "oneclass_svm",
        "auc": round(float(auc), 4),
        "f1": round(float(f1), 4),
        "recall": round(float(rec), 4),
        "fpr": round(float(fpr), 4),
        "precision": round(float(prec), 4),
    }


def _run_iforest(args: tuple) -> dict:
    X_train, X_test, y_test, if_cfg = args
    model = IsolationForest(
        n_estimators=if_cfg.get("n_estimators", 100),
        contamination=if_cfg.get("contamination", 0.05),
        random_state=if_cfg.get("random_state", 42),
    )
    model.fit(X_train)
    preds = model.predict(X_test)
    y_pred = (preds == -1).astype(int)
    scores = model.score_samples(X_test)
    auc = roc_auc_score(y_test, -scores) if len(np.unique(y_test)) > 1 else 0.0
    f1 = f1_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    prec = precision_score(y_test, y_pred, zero_division=0)
    tn = np.sum((y_test == 0) & (y_pred == 0))
    fp = np.sum((y_test == 0) & (y_pred == 1))
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "method": "isolation_forest",
        "auc": round(float(auc), 4),
        "f1": round(float(f1), 4),
        "recall": round(float(rec), 4),
        "fpr": round(float(fpr), 4),
        "precision": round(float(prec), 4),
    }


def run_baselines(
    features: np.ndarray, labels: np.ndarray, config: dict | None = None
) -> list[dict]:
    """Train SVM + IF on normal data, evaluate on all. Returns list of result dicts with 'method' key."""
    _cfg = config or {}
    svm_cfg = _cfg.get("baselines", {}).get("oneclass_svm", {})
    if_cfg = _cfg.get("baselines", {}).get("isolation_forest", {})

    prepared = _prepare_train_test(features, labels)
    if prepared is None:
        logger.warning("No normal samples for baseline training")
        return []

    X_train, X_test, y_test = prepared

    if len(np.unique(y_test)) < 2:
        logger.warning("Only one class in labels — baselines cannot evaluate")
        return []

    results = []
    svm_args = (X_train, X_test, y_test, svm_cfg)
    if_args = (X_train, X_test, y_test, if_cfg)

    with ProcessPoolExecutor(max_workers=2) as pool:
        fut_svm = pool.submit(_run_svm, svm_args)
        fut_if = pool.submit(_run_iforest, if_args)
        for name, fut in [("oneclass_svm", fut_svm), ("isolation_forest", fut_if)]:
            try:
                r = fut.result()
                results.append(r)
            except Exception as e:
                logger.warning(f"{name} failed: {e}")

    return results
