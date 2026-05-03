"""DAPT2020 baselines: extract CICFlowMeter features and delegate to shared_baselines."""

from __future__ import annotations

import logging

import numpy as np

from src.dapt_loader import get_numeric_features, load_dapt2020
from src.baselines.shared_baselines import run_baselines

logger = logging.getLogger(__name__)


def run_dapt_baselines(
    data_dir: str = "data/DAPT2020",
    max_rows: int | None = None,
    config: dict | None = None,
) -> list[dict]:
    df = load_dapt2020(data_dir)
    if max_rows is not None:
        df = df.head(max_rows)
    logger.info(f"Loaded DAPT2020 data: {len(df)} rows")

    feature_cols = get_numeric_features(df)
    if not feature_cols:
        logger.warning("No numeric features found in DAPT DataFrame")
        return []

    features = df[feature_cols].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    labels = df["is_lateral_movement"].values.astype(np.float64)

    logger.info(f"DAPT baselines: {len(features):,} rows, {len(feature_cols)} features")
    return run_baselines(features, labels, config)
