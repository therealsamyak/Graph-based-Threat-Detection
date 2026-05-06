"""DAPT2020 baselines: build graph, extract features, delegate to shared_baselines."""

from __future__ import annotations

import logging

import numpy as np

from src.baselines.shared_baselines import SCORING_FEATURE_COLUMNS, run_baselines
from src.data.dapt import load_dapt2020
from src.features import extract_all_features
from src.utils import FLOW_AGG_COLUMNS, build_dapt_graph, compute_edge_pair_names

logger = logging.getLogger(__name__)


def run_dapt_baselines(
    data_dir: str = "data/DAPT2020",
    max_rows: int | None = None,
    config: dict | None = None,
) -> list[dict]:
    _cfg = config or {}
    df = load_dapt2020(data_dir)
    if max_rows is not None:
        df = df.head(max_rows)
    logger.info(f"DAPT baselines: loaded {len(df)} rows")

    g, grouped = build_dapt_graph(df, FLOW_AGG_COLUMNS)
    logger.info(f"DAPT baselines: {g.vcount():,} nodes, {g.ecount():,} edges")

    all_feat = extract_all_features(g, config=_cfg)
    edge_features = all_feat["edge_features"]

    gt_map: dict[tuple[str, str], int] = {}
    for _, row in grouped.iterrows():
        pair = (str(row["Src IP"]), str(row["Dst IP"]))
        if pair not in gt_map:
            gt_map[pair] = int(row.get("is_lateral_movement", 0))

    edge_pair_names = compute_edge_pair_names(g)
    labels = np.array([float(gt_map.get(pair, 0)) for pair in edge_pair_names])

    mask = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )

    available = [c for c in SCORING_FEATURE_COLUMNS if c in edge_features.columns]
    if not available:
        logger.warning("No scoring feature columns found in edge_features")
        return []

    features = edge_features[available].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    features_valid = features[mask]
    labels_valid = labels[mask]

    logger.info(
        f"DAPT baselines: {len(features_valid):,} edges, {available} features"
    )
    return run_baselines(features_valid, labels_valid, config)
