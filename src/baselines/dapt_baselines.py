"""DAPT2020 sklearn baselines: OneClassSVM and IsolationForest for lateral movement detection."""

import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

from src.baselines.dapt_loader import get_numeric_features, load_dapt2020

logger = logging.getLogger(__name__)


def _prepare_features(df: pd.DataFrame):
    feature_cols = get_numeric_features(df)
    if not feature_cols:
        raise ValueError("No numeric features found in DataFrame")

    features = df[feature_cols].values.astype(np.float64)
    # Replace inf/nan with 0
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    labels = df["Stage"].astype(str).str.contains(
        "Lateral Movement", case=False, na=False
    ).astype(int)

    train_mask = labels == 0

    scaler = StandardScaler()
    X_train = scaler.fit_transform(features[train_mask])
    X_test = scaler.transform(features)

    return X_train, X_test, labels


def _evaluate(y_true: np.ndarray, y_pred: np.ndarray, method_name: str) -> dict:
    # y_pred: True = anomaly detected (predicted as attack)
    auc = roc_auc_score(y_true, y_pred.astype(float))
    f1 = f1_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    precision = precision_score(y_true, y_pred, zero_division=0)

    # FPR: false positive rate = FP / (FP + TN)
    tn = np.sum((y_true == 0) & (y_pred == 0))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    return {
        "method_name": method_name,
        "auc": round(auc, 4),
        "f1": round(f1, 4),
        "recall": round(recall, 4),
        "fpr": round(fpr, 4),
        "precision": round(precision, 4),
    }


def run_oneclass_svm(df: pd.DataFrame) -> dict:
    """Run OneClassSVM baseline for lateral movement detection.

    Trains on normal traffic, predicts on all data.
    OneClassSVM returns 1 for normal, -1 for anomaly.
    """
    X_train, X_test, y_test = _prepare_features(df)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = OneClassSVM(kernel="rbf", gamma="scale", nu=0.05)
        model.fit(X_train)

    # predict: 1 = normal, -1 = anomaly → convert to binary anomaly flag
    predictions = model.predict(X_test)
    y_pred = (predictions == -1).astype(int)

    return _evaluate(y_test.values, y_pred, "oneclass_svm")


def run_isolation_forest(df: pd.DataFrame) -> dict:
    """Run IsolationForest baseline for lateral movement detection.

    Trains on normal traffic, predicts on all data.
    IsolationForest returns 1 for normal, -1 for anomaly.
    """
    X_train, X_test, y_test = _prepare_features(df)

    model = IsolationForest(
        n_estimators=100,
        contamination=0.05,
        random_state=42,
        n_jobs=-1,
    )
    model.fit(X_train)

    # predict: 1 = normal, -1 = anomaly → convert to binary anomaly flag
    predictions = model.predict(X_test)
    y_pred = (predictions == -1).astype(int)

    return _evaluate(y_test.values, y_pred, "isolation_forest")


def run_dapt_baselines(data_dir: str = "data/DAPT2020") -> list[dict]:
    """Run all DAPT2020 sklearn baselines.

    Args:
        data_dir: Path to DAPT2020 directory.

    Returns:
        List of result dicts with keys: method_name, auc, f1, recall, fpr, precision.
    """
    df = load_dapt2020(data_dir)
    logger.info(f"Loaded DAPT2020 data: {len(df)} rows")

    baselines = [
        ("OneClassSVM", run_oneclass_svm),
        ("IsolationForest", run_isolation_forest),
    ]

    results = []
    for name, fn in baselines:
        try:
            logger.info(f"Running {name} baseline...")
            result = fn(df)
            results.append(result)
            logger.info(f"{name}: AUC={result['auc']:.4f}, F1={result['f1']:.4f}")
        except Exception as e:
            logger.warning(f"{name} failed: {e}")
            continue

    return results
