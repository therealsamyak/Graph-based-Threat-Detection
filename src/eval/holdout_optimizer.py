"""Held-out evaluation of WeightOptimizer."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.feature_audit.loader import load_feature_frame
from src.feature_audit.scorer import stratified_split
from src.optimization.optimizer import RANK_TRANSFORM_FEATURES, WeightOptimizer

logger = logging.getLogger("optimize_weights_holdout")


DEFAULT_FEATURES = [
    "is_ntlm",
    "edge_rarity",
    "dst_in_degree",
    "is_network_logon",
    "is_success_auth",
]


def _score_with_weights(features_df: pd.DataFrame, weights: dict[str, float]) -> np.ndarray:
    score = np.zeros(len(features_df), dtype=float)
    for name, w in weights.items():
        if name not in features_df.columns:
            raise KeyError(f"Feature {name!r} not present in eval feature matrix")
        col = features_df[name].to_numpy(dtype=float, copy=True)
        if name in RANK_TRANSFORM_FEATURES:
            col = pd.Series(col).rank(pct=True).to_numpy()
        score += w * col
    return score


def _transform_for_lr(features_df: pd.DataFrame, feature_list: list[str]) -> np.ndarray:
    cols: list[np.ndarray] = []
    for name in feature_list:
        col = features_df[name].to_numpy(dtype=float, copy=True)
        if name in RANK_TRANSFORM_FEATURES:
            col = pd.Series(col).rank(pct=True).to_numpy()
        cols.append(col)
    return np.column_stack(cols)


def _logistic_regression_baseline(
    cal_features: pd.DataFrame,
    cal_labels: np.ndarray,
    eval_features: pd.DataFrame,
    eval_labels: np.ndarray,
    feature_list: list[str],
    seed: int,
) -> dict:
    X_cal = _transform_for_lr(cal_features, feature_list)
    X_eval = _transform_for_lr(eval_features, feature_list)
    scaler = StandardScaler().fit(X_cal)
    X_cal_s = scaler.transform(X_cal)
    X_eval_s = scaler.transform(X_eval)

    lr = LogisticRegression(
        class_weight="balanced",
        max_iter=2000,
        random_state=seed,
        solver="liblinear",
    )
    lr.fit(X_cal_s, cal_labels)
    cal_scores = lr.predict_proba(X_cal_s)[:, 1]
    eval_scores = lr.predict_proba(X_eval_s)[:, 1]
    cal_auc = float(roc_auc_score(cal_labels, cal_scores))
    eval_auc = float(roc_auc_score(eval_labels, eval_scores))
    coefs = {name: float(lr.coef_[0, i]) for i, name in enumerate(feature_list)}
    return {
        "auc_calibration": cal_auc,
        "auc_eval": eval_auc,
        "overfit_gap_cal_minus_eval": cal_auc - eval_auc,
        "intercept": float(lr.intercept_[0]),
        "coefficients": coefs,
    }


def _full_set_baseline_auc(features_df: pd.DataFrame, labels: np.ndarray, feature_list: list[str]) -> float:
    n = len(feature_list)
    eq_w = {name: 1.0 / n for name in feature_list}
    scores = _score_with_weights(features_df[feature_list], eq_w)
    return float(roc_auc_score(labels, scores))


def run_holdout_optimization(
    run_dir: Path,
    feature_list: list[str] | None = None,
    holdout_frac: float = 0.5,
    seed: int = 42,
    output_dir: Path | None = None,
) -> dict:
    if feature_list is None:
        feature_list = list(DEFAULT_FEATURES)

    logger.info(f"Features to optimize: {feature_list}")

    logger.info(f"Loading features from {run_dir}")
    features_full_df, labels_full, available_cols = load_feature_frame(run_dir)

    missing = [f for f in feature_list if f not in features_full_df.columns]
    if missing:
        logger.error(f"Requested features not in loaded matrix: {missing}")
        logger.error(f"Available columns ({len(available_cols)}): {available_cols[:10]}{'...' if len(available_cols) > 10 else ''}")
        raise ValueError(f"Requested features not in loaded matrix: {missing}")

    features_df = features_full_df[feature_list].reset_index(drop=True)
    labels = labels_full.astype(np.float64)
    logger.info(f"Loaded matrix: {len(features_df):,} edges, {int(labels.sum())} red-team")

    cal_idx, eval_idx = stratified_split(
        features_df.to_numpy(), labels, holdout_frac=holdout_frac, seed=seed
    )
    logger.info(
        f"Stratified split (seed {seed}): "
        f"calibration {len(cal_idx):,} edges ({int(labels[cal_idx].sum())} red-team), "
        f"eval {len(eval_idx):,} edges ({int(labels[eval_idx].sum())} red-team)"
    )

    full_auc_equal = _full_set_baseline_auc(features_df, labels, feature_list)
    cal_features = features_df.iloc[cal_idx].reset_index(drop=True)
    cal_labels = labels[cal_idx]
    eval_features = features_df.iloc[eval_idx].reset_index(drop=True)
    eval_labels = labels[eval_idx]

    optimizer = WeightOptimizer(cal_features, cal_labels, feature_list)
    logger.info("Running Nelder-Mead on calibration half...")
    result = optimizer.optimize()
    weights = {name: float(result[name]) for name in feature_list}

    cal_auc_optimized = float(result["auc"])
    eval_scores = _score_with_weights(eval_features, weights)
    eval_auc_optimized = float(roc_auc_score(eval_labels, eval_scores))

    full_scores = _score_with_weights(features_df, weights)
    full_auc_optimized = float(roc_auc_score(labels, full_scores))

    gap = cal_auc_optimized - eval_auc_optimized
    rel_gap = gap / max(cal_auc_optimized, 1e-9)

    logger.info("Running logistic-regression baseline on calibration half...")
    lr_result = _logistic_regression_baseline(
        cal_features, cal_labels, eval_features, eval_labels, feature_list, seed
    )
    lr_gap = lr_result["overfit_gap_cal_minus_eval"]
    delta_vs_lr = eval_auc_optimized - lr_result["auc_eval"]

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_run_dir": str(run_dir.resolve()),
        "features": feature_list,
        "holdout_frac": holdout_frac,
        "seed": seed,
        "n_calibration": int(len(cal_idx)),
        "n_eval": int(len(eval_idx)),
        "redteam_calibration": int(cal_labels.sum()),
        "redteam_eval": int(eval_labels.sum()),
        "optimizer": {
            "method": "nelder-mead",
            "weights": weights,
            "auc_calibration": cal_auc_optimized,
            "auc_eval": eval_auc_optimized,
            "auc_full_for_reference": full_auc_optimized,
            "auc_full_equal_weights_baseline": full_auc_equal,
            "overfit_gap_cal_minus_eval": gap,
            "overfit_gap_relative": rel_gap,
            "iterations": int(result["iterations"]),
            "converged": bool(result["converged"]),
            "seconds": float(result["total_time_seconds"]),
        },
        "logistic_regression": lr_result,
        "delta_eval_auc_optimizer_minus_lr": delta_vs_lr,
    }

    logger.info("=" * 70)
    logger.info("Held-out comparison: optimizer vs logistic regression")
    logger.info(f"  Optimizer  cal AUC: {cal_auc_optimized:.6f}  eval AUC: {eval_auc_optimized:.6f}  (gap {gap:+.6f})")
    logger.info(f"  LR         cal AUC: {lr_result['auc_calibration']:.6f}  eval AUC: {lr_result['auc_eval']:.6f}  (gap {lr_gap:+.6f})")
    logger.info(f"  Eval delta (optimizer - LR): {delta_vs_lr:+.6f}")
    logger.info(f"  Equal-weights reference full AUC: {full_auc_equal:.6f}")
    logger.info("=" * 70)

    if output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = Path("analysis_results") / ts
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = output_dir.resolve()
    out_path = out_dir / "holdout_results.json"
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"Wrote {out_path}")

    return payload
