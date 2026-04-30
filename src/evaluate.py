"""Metrics computation pipeline for lateral movement detection."""

import numpy as np
import pandas as pd
from sklearn.metrics import (
    roc_auc_score,
    roc_curve,
)


def compute_metrics(
    scores: pd.Series, labels: pd.Series, threshold: float = 0.5
) -> dict:
    """Compute classification metrics at a given threshold."""
    predictions = (scores > threshold).astype(int)
    tp = int(((predictions == 1) & (labels == 1)).sum())
    fp = int(((predictions == 1) & (labels == 0)).sum())
    tn = int(((predictions == 0) & (labels == 0)).sum())
    fn = int(((predictions == 0) & (labels == 1)).sum())

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    accuracy = (tp + tn) / (tp + fp + tn + fn) if (tp + fp + tn + fn) > 0 else 0.0

    return {
        "recall": float(recall),
        "precision": float(precision),
        "f1": float(f1),
        "fpr": float(fpr),
        "accuracy": float(accuracy),
        "tp": tp,
        "fp": fp,
        "tn": tn,
        "fn": fn,
    }


def compute_detection_latency(
    event_times: pd.Series,
    redteam_times: pd.Series,
    detected: pd.Series,
) -> float:
    """Time (seconds) from first red-team event to first detected red-team event."""
    if redteam_times.empty:
        return float("inf")

    first_red_time = redteam_times.min()

    red_set = set(redteam_times.values)
    for t, d in zip(event_times.values, detected.values):
        if d and t in red_set:
            return float(t - first_red_time)

    return float("inf")


def compute_throughput(n_events: int, elapsed_seconds: float) -> float:
    """Events processed per second."""
    if elapsed_seconds <= 0:
        return 0.0
    return float(n_events / elapsed_seconds)


def evaluate_method(
    scores: pd.Series,
    labels: pd.Series,
    event_times: pd.Series | None = None,
    redteam_times: pd.Series | None = None,
    elapsed_seconds: float = 1.0,
) -> dict:
    """Orchestrate all metrics computation for a detection method."""
    threshold = float(scores.quantile(0.95))
    metrics = compute_metrics(scores, labels, threshold)

    n_classes = labels.nunique()
    if n_classes < 2:
        auc = 0.5
    else:
        auc = float(roc_auc_score(labels, scores))

    if event_times is not None and redteam_times is not None:
        predictions = (scores > threshold).astype(int)
        detected = predictions.astype(bool)
        latency = compute_detection_latency(event_times, redteam_times, detected)
    else:
        latency = float("inf")

    throughput = compute_throughput(len(scores), elapsed_seconds)

    return {
        "recall": metrics["recall"],
        "precision": metrics["precision"],
        "f1": metrics["f1"],
        "fpr": metrics["fpr"],
        "accuracy": metrics["accuracy"],
        "detection_latency": latency,
        "throughput": throughput,
        "threshold": threshold,
        "auc": auc,
    }


def compute_roc_curve(
    scores: pd.Series, labels: pd.Series
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Compute ROC curve points."""
    if labels.nunique() < 2:
        return np.array([0, 1]), np.array([0, 1]), np.array([1, 0])
    fpr, tpr, thresholds = roc_curve(labels, scores)
    return fpr, tpr, thresholds
