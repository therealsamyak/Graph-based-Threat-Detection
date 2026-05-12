"""Held-out AUC scoring for individual features."""

from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score

from src.feature_audit.types import FeatureResult


def stratified_split(
    X: np.ndarray, y: np.ndarray, holdout_frac: float = 0.5, seed: int = 42
) -> tuple[np.ndarray, np.ndarray]:
    if not 0.0 < holdout_frac < 1.0:
        raise ValueError("holdout_frac must be between 0 and 1")
    if len(X) != len(y):
        raise ValueError("X and y must have the same row count")

    rng = np.random.default_rng(seed)
    calibration_parts: list[np.ndarray] = []
    eval_parts: list[np.ndarray] = []
    for label in np.unique(y):
        idx = np.flatnonzero(y == label)
        rng.shuffle(idx)
        eval_n = int(round(len(idx) * holdout_frac))
        eval_parts.append(idx[:eval_n])
        calibration_parts.append(idx[eval_n:])
    calibration = np.concatenate(calibration_parts)
    evaluation = np.concatenate(eval_parts)
    rng.shuffle(calibration)
    rng.shuffle(evaluation)
    return calibration, evaluation


def _maybe_log1p(values: np.ndarray, feature: str, log1p_cols: set[str]) -> np.ndarray:
    if feature in log1p_cols:
        return np.log1p(np.clip(values, a_min=0.0, a_max=None))
    return values


def compute_feature_aucs(
    X: np.ndarray, y: np.ndarray, columns: list[str], log1p_cols: list[str] | None = None
) -> list[FeatureResult]:
    log_cols = set(log1p_cols or [])
    results: list[FeatureResult] = []
    red_mask = y == 1
    benign_mask = y == 0
    for i, feature in enumerate(columns):
        values = _maybe_log1p(X[:, i].astype(float), feature, log_cols)
        mean_redteam = float(values[red_mask].mean()) if red_mask.any() else 0.0
        mean_benign = float(values[benign_mask].mean()) if benign_mask.any() else 0.0
        delta = mean_redteam - mean_benign
        if len(np.unique(y)) < 2 or len(np.unique(values)) < 2:
            auc = 0.5
        else:
            raw_auc = float(roc_auc_score(y, values))
            auc = 1.0 - raw_auc if delta < 0.0 else raw_auc
        results.append(
            FeatureResult(
                feature=feature,
                auc=auc,
                n_unique=int(len(np.unique(values))),
                variance=float(np.var(values)),
                mean_redteam=mean_redteam,
                mean_benign=mean_benign,
                delta_mean=delta,
                is_duplicate_of=None,
                selected=False,
            )
        )
    return sorted(results, key=lambda r: r.auc, reverse=True)


def select_features(results: list[FeatureResult], min_auc: float = 0.7) -> list[str]:
    return [result.feature for result in results if result.auc >= min_auc and result.is_duplicate_of is None]


def mark_duplicates(
    results: list[FeatureResult], duplicate_pairs: list[tuple[str, str]]
) -> list[FeatureResult]:
    duplicate_map = {duplicate: original for original, duplicate in duplicate_pairs}
    return [
        FeatureResult(
            feature=result.feature,
            auc=result.auc,
            n_unique=result.n_unique,
            variance=result.variance,
            mean_redteam=result.mean_redteam,
            mean_benign=result.mean_benign,
            delta_mean=result.delta_mean,
            is_duplicate_of=duplicate_map.get(result.feature),
            selected=result.selected,
        )
        for result in results
    ]


def evaluate_selected(
    X: np.ndarray,
    y: np.ndarray,
    cal_idx: np.ndarray,
    eval_idx: np.ndarray,
    columns: list[str],
    selected_cols: list[str],
) -> dict[str, float]:
    del cal_idx
    metrics: dict[str, float] = {}
    eval_y = y[eval_idx]
    if len(np.unique(eval_y)) < 2:
        return {feature: 0.5 for feature in selected_cols}
    for feature in selected_cols:
        col_idx = columns.index(feature)
        values = X[eval_idx, col_idx]
        raw_auc = float(roc_auc_score(eval_y, values)) if len(np.unique(values)) > 1 else 0.5
        metrics[feature] = max(raw_auc, 1.0 - raw_auc)
    return metrics
