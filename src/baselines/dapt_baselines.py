"""DAPT2020 baselines: build graph, extract graph features, delegate to shared_baselines."""

from __future__ import annotations

import logging

import igraph as ig
import numpy as np

from src.baselines.shared_baselines import SCORING_FEATURE_COLUMNS, run_baselines
from src.data.dapt import load_dapt2020
from src.features.graph import extract_all_features

logger = logging.getLogger(__name__)

FLOW_AGG_COLUMNS = [
    "Flow Duration", "Total Fwd Packet", "Total Bwd packets",
    "Total Length of Fwd Packet", "Total Length of Bwd Packet",
    "Flow Bytes/s", "Flow Packets/s",
    "Fwd Packet Length Mean", "Bwd Packet Length Mean",
    "Fwd Packets/s", "Bwd Packets/s",
    "Flow IAT Mean", "Packet Length Mean",
]


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

    agg_cols_available = [c for c in FLOW_AGG_COLUMNS if c in df.columns]
    group_cols = ["Src IP", "Dst IP"]

    agg_dict: dict = {"is_lateral_movement": "max"}
    for c in agg_cols_available:
        agg_dict[c] = "mean"
    if "Protocol" in df.columns:
        agg_dict["Protocol"] = "first"

    grouped = df.groupby(group_cols, as_index=False).agg(agg_dict)
    logger.info(f"DAPT baselines: {len(grouped)} unique src-dst pairs")

    g = ig.Graph(directed=True)
    node_set: set[str] = set()

    for _, row in grouped.iterrows():
        src = str(row["Src IP"])
        dst = str(row["Dst IP"])
        if src not in node_set:
            g.add_vertex(src, node_type="computer", is_machine=True)
            node_set.add(src)
        if dst not in node_set:
            g.add_vertex(dst, node_type="computer", is_machine=True)
            node_set.add(dst)

        edge_attrs = {"type": "flow", "weight": 1}
        for c in agg_cols_available:
            val = row.get(c)
            if val is not None:
                try:
                    edge_attrs[c] = float(val)
                except (ValueError, TypeError):
                    pass
        if "Protocol" in row.index:
            edge_attrs["protocol"] = str(row["Protocol"])
        g.add_edge(src, dst, **edge_attrs)

    logger.info(f"DAPT baselines: {g.vcount():,} nodes, {g.ecount():,} edges")

    all_feat = extract_all_features(g, config=_cfg)
    edge_features = all_feat["edge_features"]

    gt_map = {}
    for _, row in grouped.iterrows():
        pair = (str(row["Src IP"]), str(row["Dst IP"]))
        if pair not in gt_map:
            gt_map[pair] = int(row.get("is_lateral_movement", 0))

    edge_pair_names = [
        (g.vs[g.es[i].source]["name"], g.vs[g.es[i].target]["name"])
        for i in range(g.ecount())
    ]
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
