"""Edge-level anomaly scoring."""

from __future__ import annotations

import numpy as np
import pandas as pd
import igraph as ig


def score_edges(
    g: ig.Graph,
    edge_features: pd.DataFrame,
    weights: dict[str, float] | None = None,
    config: dict | None = None,
) -> pd.Series:
    """Score edges via discriminative features: NTLM, network logon, edge rarity.

    Edges where either endpoint contains "@" (user edges) or where src == dst
    (self-loops) receive score 0.0 — these have zero red-team signal.
    Auth edges use weighted combo of NTLM, network logon, and rarity rank;
    flow edges use flow-specific features (rarity, unusual dst port, protocol rarity).
    Optionally applies auth_weight_multiplier for combined method and temporal decay.
    Returns pd.Series indexed by edge index (int), values in [0,1].
    """
    if weights is None:
        weights = {"is_ntlm": 0.4, "is_network_logon": 0.3, "edge_rarity": 0.3}

    _cfg = config or {}
    scoring_cfg = _cfg.get("scoring", {})
    flow_weights = scoring_cfg.get("flow_weights", {"edge_rarity": 0.4, "is_unusual_dst_port": 0.3, "protocol_rarity": 0.3})
    auth_weight_multiplier = scoring_cfg.get("auth_weight_multiplier", 1.0)

    n = g.ecount()
    if n == 0:
        return pd.Series([], index=pd.Index([], name="edge_index"), dtype=float)

    rarity_rank = edge_features["edge_rarity"].rank(pct=True).values

    mask_valid = (
        (edge_features["is_self_loop"].values == 0.0)
        & (edge_features["is_user_edge"].values == 0.0)
    )

    is_auth = np.array([
        g.es[i].attributes().get("type", "flow") == "auth" for i in range(n)
    ])

    w_ntlm = weights.get("is_ntlm", 0.4)
    w_net = weights.get("is_network_logon", 0.3)
    w_rar = weights.get("edge_rarity", 0.3)

    is_ntlm = edge_features["is_ntlm"].values
    is_network = edge_features["is_network_logon"].values

    has_flow_features = (
        "is_unusual_dst_port" in edge_features.columns
        and "protocol_rarity" in edge_features.columns
    )
    if has_flow_features:
        fw_rar = flow_weights.get("edge_rarity", 0.4)
        fw_port = flow_weights.get("is_unusual_dst_port", 0.3)
        fw_proto = flow_weights.get("protocol_rarity", 0.3)
        is_unusual_port = edge_features["is_unusual_dst_port"].values
        protocol_rarity = edge_features["protocol_rarity"].rank(pct=True).values
        flow_score = fw_rar * rarity_rank + fw_port * is_unusual_port + fw_proto * protocol_rarity
    else:
        flow_score = rarity_rank

    raw = np.where(
        is_auth,
        w_ntlm * is_ntlm + w_net * is_network + w_rar * rarity_rank,
        flow_score,
    )

    if auth_weight_multiplier != 1.0:
        raw = np.where(is_auth, raw * auth_weight_multiplier, raw)

    if "temporal_decay_weight" in edge_features.columns:
        decay = edge_features["temporal_decay_weight"].values
        raw = raw * decay

    raw = np.where(mask_valid, raw, 0.0)

    return pd.Series(raw, index=pd.Index(range(n), name="edge_index"))


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
