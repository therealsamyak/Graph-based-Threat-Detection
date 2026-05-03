"""LANL-2015 baselines: extract edge features and delegate to shared_baselines."""

from __future__ import annotations

import logging

import igraph as ig
import numpy as np
import pandas as pd

from src.baselines.shared_baselines import run_baselines

logger = logging.getLogger(__name__)

FEATURE_COLUMNS = [
    "edge_rarity",
    "src_out_degree",
    "dst_in_degree",
    "is_ntlm",
    "is_network_logon",
    "is_success_auth",
    "source_fan_out",
    "weight_norm",
    "is_unusual_dst_port",
    "protocol_rarity",
    "byte_per_packet",
    "duration_zscore",
]


def run_lanl_baselines(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    config: dict | None = None,
) -> list[dict]:
    available = [c for c in FEATURE_COLUMNS if c in edge_features.columns]
    if not available:
        logger.warning("No tabular feature columns found in edge_features")
        return []

    mask = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )

    features = edge_features[available].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    edge_pair_names = [
        (g.vs[g.es[i].source]["name"], g.vs[g.es[i].target]["name"])
        for i in range(g.ecount())
    ]
    labels = np.array([1.0 if pair in red_pairs else 0.0 for pair in edge_pair_names])

    features_valid = features[mask]
    labels_valid = labels[mask]

    logger.info(
        f"LANL baselines: {len(features_valid):,} edges, {available} features"
    )

    return run_baselines(features_valid, labels_valid, config)
