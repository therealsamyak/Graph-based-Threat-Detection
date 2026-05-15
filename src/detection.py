"""Threshold optimization and detection metrics."""

from __future__ import annotations

import logging

import numpy as np
from sklearn.metrics import roc_auc_score

from src.types import DetectionParams

logger = logging.getLogger(__name__)


def optimize_threshold(
    params: DetectionParams,
    threshold_mode: str = "auto_optimize",
    search_range: list[float] | None = None,
    default_percentile: float = 90,
) -> tuple[float, float]:
    """Auto-optimize threshold by sweeping percentiles to maximize F1.

    Returns (threshold, percentile_used).
    """
    if search_range is None:
        search_range = [90, 95, 97, 99, 99.5, 99.9]

    edge_scores = params.edge_scores
    mask_valid = params.mask_valid
    edge_pair_names = params.edge_pair_names
    positive_pairs_in_graph = params.positive_pairs_in_graph
    all_positive_pairs = params.all_positive_pairs

    scoring_scores = edge_scores[mask_valid]
    best_pct = default_percentile

    if (
        threshold_mode == "auto_optimize"
        and len(scoring_scores) > 0
        and scoring_scores.std() > 1e-10
    ):
        best_f1 = -1.0
        best_threshold = float(scoring_scores.max()) + 0.01

        for pct in search_range:
            thr = float(np.nextafter(np.percentile(scoring_scores.values, pct), -np.inf))
            anom_mask = mask_valid & (edge_scores > thr)
            anom_pairs_test = {
                edge_pair_names[i]
                for i in range(len(edge_pair_names))
                if anom_mask.iloc[i]
            }
            detected_test = anom_pairs_test & positive_pairs_in_graph
            rec = (
                len(detected_test) / len(all_positive_pairs)
                if all_positive_pairs
                else 0.0
            )
            prec = len(detected_test) / max(len(anom_pairs_test), 1)
            f1_val = 2 * rec * prec / (rec + prec) if (rec + prec) > 0 else 0.0
            if f1_val > best_f1:
                best_f1 = f1_val
                best_threshold = thr
                best_pct = pct

        threshold = best_threshold
        logger.info(
            f"Auto-optimized: percentile={best_pct}, threshold={threshold:.4f}, F1={best_f1:.4f}"
        )
    elif len(scoring_scores) > 0:
        threshold = float(np.nextafter(np.percentile(scoring_scores.values, default_percentile), -np.inf))
        if scoring_scores.std() < 1e-10:
            logger.warning("All edge scores identical — no anomalies detectable")
            threshold = float(scoring_scores.max()) + 0.01
    else:
        threshold = 0.5

    return threshold, best_pct


def compute_pair_metrics(
    params: DetectionParams,
    threshold: float,
) -> dict:
    """Compute recall, FPR, F1, precision, AUC at pair level.

    Returns dict with keys: recall, fpr, f1, precision, auc, anomalous_pairs,
    detected_pairs, anomalous_mask.
    """
    edge_scores = params.edge_scores
    mask_valid = params.mask_valid
    edge_pair_names = params.edge_pair_names
    all_graph_edges = params.all_graph_edges
    positive_pairs_in_graph = params.positive_pairs_in_graph
    all_positive_pairs = params.all_positive_pairs

    anomalous_mask = mask_valid & (edge_scores > threshold)
    anomalous_pairs: set[tuple[str, str]] = {
        edge_pair_names[i]
        for i in range(len(edge_pair_names))
        if anomalous_mask.iloc[i]
    }

    detected_pairs = anomalous_pairs & positive_pairs_in_graph
    recall = (
        len(detected_pairs) / len(all_positive_pairs)
        if all_positive_pairs
        else 0.0
    )
    true_negatives = len(all_graph_edges - anomalous_pairs - positive_pairs_in_graph)
    false_positives = len(anomalous_pairs - positive_pairs_in_graph)
    fpr = false_positives / max(false_positives + true_negatives, 1)
    precision = len(detected_pairs) / max(len(anomalous_pairs), 1)
    f1 = (
        2 * recall * precision / (recall + precision)
        if (recall + precision) > 0
        else 0.0
    )

    edge_labels = np.array(
        [1.0 if pair in positive_pairs_in_graph else 0.0 for pair in edge_pair_names]
    )
    valid_labels = edge_labels[mask_valid]
    valid_scores = edge_scores.values[mask_valid]
    try:
        if len(np.unique(valid_labels)) > 1:
            auc = float(roc_auc_score(valid_labels, valid_scores))
        else:
            auc = 0.0
            logger.warning("Only one class present in valid edges — AUC undefined")
    except ValueError:
        auc = 0.0
        logger.warning("AUC computation failed")

    return {
        "recall": recall,
        "fpr": fpr,
        "f1": f1,
        "precision": precision,
        "auc": auc,
        "anomalous_pairs": anomalous_pairs,
        "detected_pairs": detected_pairs,
        "anomalous_mask": anomalous_mask,
    }
