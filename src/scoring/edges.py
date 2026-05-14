"""Edge-level anomaly scoring."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
import igraph as ig

logger = logging.getLogger(__name__)


def score_edges(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    weights: dict[str, float] | None = None,
    config: dict | None = None,
) -> pd.Series:
    """Score edges via discriminative features with unified weighted sum.

    Uses a simple weighted sum of features from the weights dict. If weights is None,
    defaults to equal weights for the top-5 features: is_ntlm, source_fan_out,
    dst_in_degree, is_network_logon, dst_fan_out_ratio.

    Edges where either endpoint contains "@" (user edges) or where src == dst
    (self-loops) receive score 0.0 — these have zero red-team signal.

    Features named 'edge_rarity' or 'protocol_rarity' are rank-transformed (pct=True).

    Returns pd.Series indexed by edge index (int), values in [0,1].
    """
    _cfg = config or {}
    scoring_cfg = _cfg.get("scoring", {})
    output_dir = _cfg.get("output_dir") or scoring_cfg.get("output_dir")

    if weights is None:
        weights = {
            "is_ntlm": 0.2,
            "source_fan_out": 0.2,
            "dst_in_degree": 0.2,
            "is_network_logon": 0.2,
            "dst_fan_out_ratio": 0.2,
        }

    n = g.ecount()
    if n == 0:
        return pd.Series([], index=pd.Index([], name="edge_index"), dtype=float)

    logger.info(f"Scoring edges: {n:,} edges, {len(weights)} features")
    logger.info(f"Weights used: {weights}")

    mask_valid = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )
    valid_count = mask_valid.sum()
    invalid_count = n - valid_count

    logger.info(f"Valid edges: {valid_count:,} ({valid_count/n:.1%}), "
                f"invalid (self-loop/user-edge): {invalid_count:,} ({invalid_count/n:.1%})")

    score = np.zeros(n)
    per_feature_contribution = {}

    for feat_name, weight in weights.items():
        if feat_name not in edge_features.columns:
            logger.warning(f"Feature '{feat_name}' not in edge_features columns, skipping")
            continue

        feat_values = edge_features[feat_name].values

        if feat_name in ("edge_rarity", "protocol_rarity"):
            feat_values = pd.Series(feat_values).rank(pct=True).values
            logger.info(f"Applied rank transform to '{feat_name}'")

        contribution = weight * feat_values
        per_feature_contribution[feat_name] = float(contribution[mask_valid].mean()) if valid_count > 0 else 0.0
        score += contribution

        logger.info(f"  {feat_name}: weight={weight:.3f}, mean={feat_values[mask_valid].mean():.4f}, "
                    f"contrib_mean={contribution[mask_valid].mean():.4f}")

    score = np.where(mask_valid, score, 0.0)

    stats = {
        "min": float(score.min()),
        "max": float(score.max()),
        "mean": float(score.mean()),
        "std": float(score.std()) if score.std() > 0 else 0.0,
    }
    for p in [25, 50, 75, 90, 95, 99]:
        stats[f"p{p}"] = float(np.percentile(score, p))

    logger.info(f"Score distribution: min={stats['min']:.4f}, max={stats['max']:.4f}, "
                f"mean={stats['mean']:.4f}, std={stats['std']:.4f}")
    logger.info(f"Percentiles: p25={stats['p25']:.4f}, p50={stats['p50']:.4f}, "
                f"p75={stats['p75']:.4f}, p90={stats['p90']:.4f}, "
                f"p95={stats['p95']:.4f}, p99={stats['p99']:.4f}")

    summary = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "weights": weights,
        "feature_names": list(weights.keys()),
        "edge_count": int(n),
        "valid_count": int(valid_count),
        "invalid_count": int(invalid_count),
        "score_statistics": stats,
        "per_feature_contribution": per_feature_contribution,
    }

    if output_dir:
        results_path = Path(output_dir)
        results_path.mkdir(parents=True, exist_ok=True)
        summary_path = results_path / "scoring_summary.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)
        logger.info(f"Saved scoring summary to {summary_path}")

    return pd.Series(score, index=pd.Index(range(n), name="edge_index"))


def boost_edges_from_paths(
    edge_scores: pd.Series,
    paths: pd.DataFrame,
    boost_factor: float = 0.1,
) -> pd.Series:
    """Boost edge scores based on path scores — feeds path-level anomaly signal back into edge detection."""
    if paths.empty or boost_factor <= 0:
        return edge_scores

    boosted = edge_scores.copy()
    for _, path_row in paths.iterrows():
        path_edges = path_row.get("path_edges", [])
        path_score = path_row.get("path_score", 0.0)
        if isinstance(path_edges, list):
            for eid in path_edges:
                if eid in boosted.index:
                    boosted.iloc[eid] = min(boosted.iloc[eid] + boost_factor * path_score, 1.0)

    return boosted