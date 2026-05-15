"""Held-out evaluation of WeightOptimizer.

Wraps src.optimization.optimizer.WeightOptimizer in the held-out
calibration/evaluation split specified in
report/Feature_Selection_Analysis.md, so the reported AUC is an
unbiased estimate rather than a same-set training AUC.

The current optimizer in src/optimization/optimizer.py trains on the
full feature matrix and reports AUC on the same matrix. That estimate
is optimistically biased: the optimizer has searched the weight space
to fit the labels it is being evaluated against. To get a fair
estimate we split the data into a calibration half (used to fit the
weights) and an evaluation half (which the optimizer never sees) and
report AUC on the eval half.

Does not modify src/optimization/optimizer.py or any teammate-owned
file. Reuses the audit module's loader and stratified_split functions.

Usage:
    uv run python scripts/optimize_weights_holdout.py \
        --run-dir results/20260504_183345/combined \
        --features is_ntlm,source_fan_out,dst_in_degree,is_network_logon,dst_fan_out_ratio \
        --holdout-frac 0.5 \
        --output-dir results/<timestamp>/optimization_holdout
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.feature_audit.loader import load_feature_frame  # noqa: E402
from src.feature_audit.scorer import stratified_split  # noqa: E402
from src.optimization.optimizer import RANK_TRANSFORM_FEATURES, WeightOptimizer  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("optimize_weights_holdout")


DEFAULT_FEATURES = [
    "is_ntlm",
    "source_fan_out",
    "dst_in_degree",
    "is_network_logon",
    "dst_fan_out_ratio",
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


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True,
                        help="Cached combined run dir (e.g. results/20260504_183345/combined).")
    parser.add_argument("--features", type=str, default=",".join(DEFAULT_FEATURES),
                        help="Comma-separated feature names to optimize over.")
    parser.add_argument("--holdout-frac", type=float, default=0.5,
                        help="Fraction held out for evaluation (default: 0.5).")
    parser.add_argument("--seed", type=int, default=42,
                        help="Random seed for stratified split (default: 42).")
    parser.add_argument("--output-dir", type=Path, default=None,
                        help="Output directory for results JSON (defaults to results/<timestamp>/optimization_holdout).")
    args = parser.parse_args()

    feature_list = [f.strip() for f in args.features.split(",") if f.strip()]
    logger.info(f"Features to optimize: {feature_list}")

    logger.info(f"Loading features from {args.run_dir}")
    features_full_df, labels_full, available_cols = load_feature_frame(args.run_dir)

    missing = [f for f in feature_list if f not in features_full_df.columns]
    if missing:
        logger.error(f"Requested features not in loaded matrix: {missing}")
        logger.error(f"Available columns ({len(available_cols)}): {available_cols[:10]}{'...' if len(available_cols) > 10 else ''}")
        return 1

    features_df = features_full_df[feature_list].reset_index(drop=True)
    labels = labels_full.astype(np.float64)
    logger.info(f"Loaded matrix: {len(features_df):,} edges, {int(labels.sum())} red-team")

    cal_idx, eval_idx = stratified_split(
        features_df.to_numpy(), labels, holdout_frac=args.holdout_frac, seed=args.seed
    )
    logger.info(
        f"Stratified split (seed {args.seed}): "
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

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_run_dir": str(args.run_dir.resolve()),
        "features": feature_list,
        "holdout_frac": args.holdout_frac,
        "seed": args.seed,
        "n_calibration": int(len(cal_idx)),
        "n_eval": int(len(eval_idx)),
        "redteam_calibration": int(cal_labels.sum()),
        "redteam_eval": int(eval_labels.sum()),
        "weights": weights,
        "auc_calibration_optimized": cal_auc_optimized,
        "auc_eval_optimized": eval_auc_optimized,
        "auc_full_optimized_for_reference": full_auc_optimized,
        "auc_full_equal_weights_baseline": full_auc_equal,
        "overfit_gap_cal_minus_eval": gap,
        "overfit_gap_relative": rel_gap,
        "optimizer_iterations": int(result["iterations"]),
        "optimizer_converged": bool(result["converged"]),
        "optimizer_seconds": float(result["total_time_seconds"]),
    }

    logger.info("=" * 70)
    logger.info("Held-out optimization results")
    logger.info(f"  Calibration AUC (optimized weights, trained on cal):    {cal_auc_optimized:.6f}")
    logger.info(f"  Eval AUC        (optimized weights, evaluated on eval): {eval_auc_optimized:.6f}")
    logger.info(f"  Full AUC        (optimized weights, evaluated on full): {full_auc_optimized:.6f}")
    logger.info(f"  Full AUC        (equal weights, baseline):              {full_auc_equal:.6f}")
    logger.info(f"  Overfit gap     (cal AUC minus eval AUC):               {gap:+.6f} ({rel_gap*100:+.2f}%)")
    logger.info("=" * 70)
    if abs(gap) < 0.005:
        logger.info("  Gap < 0.005 — optimization is generalizing; the AUC is defensible.")
    elif gap > 0:
        logger.warning(f"  Gap > 0.005 — calibration AUC overstates eval performance by {gap:.4f}.")
    else:
        logger.info("  Eval AUC exceeds calibration AUC — variance favors held-out side this seed.")

    if args.output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = REPO_ROOT / "results" / ts / "optimization_holdout"
    else:
        out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "holdout_results.json"
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"Wrote {out_path}")

    return 0


def _full_set_baseline_auc(features_df: pd.DataFrame, labels: np.ndarray, feature_list: list[str]) -> float:
    n = len(feature_list)
    eq_w = {name: 1.0 / n for name in feature_list}
    scores = _score_with_weights(features_df[feature_list], eq_w)
    return float(roc_auc_score(labels, scores))


if __name__ == "__main__":
    raise SystemExit(main())
