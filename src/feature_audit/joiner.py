"""Join cached node features onto edge rows for auditing."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd


def _prefixed_node_features(node_df: pd.DataFrame, prefix: str) -> pd.DataFrame:
    data = node_df.copy()
    if "node" in data.columns:
        data = data.set_index("node")
    data.index = data.index.astype(str)
    data = data.add_prefix(prefix)
    data.index.name = "node"
    return data


def join_node_features(
    edge_df: pd.DataFrame, graph_edges_csv: Path, node_features_csv: Path
) -> pd.DataFrame:
    if not node_features_csv.exists():
        return edge_df.copy()
    if not graph_edges_csv.exists():
        raise FileNotFoundError(f"Missing required input: {graph_edges_csv}")

    edges = pd.read_csv(graph_edges_csv, usecols=["src", "dst"])
    if len(edges) != len(edge_df):
        raise ValueError(
            f"Row count mismatch: edge_features has {len(edge_df)}, graph_edges.csv has {len(edges)}"
        )
    node_df = pd.read_csv(node_features_csv)
    src_features = _prefixed_node_features(node_df, "src_")
    dst_features = _prefixed_node_features(node_df, "dst_")

    joined = edge_df.reset_index(drop=True).copy()
    src_joined = src_features.reindex(edges["src"].astype(str).values).reset_index(drop=True)
    dst_joined = dst_features.reindex(edges["dst"].astype(str).values).reset_index(drop=True)
    src_joined = src_joined.drop(columns=[c for c in src_joined.columns if c in joined.columns])
    dst_joined = dst_joined.drop(columns=[c for c in dst_joined.columns if c in joined.columns])
    return pd.concat([joined, src_joined, dst_joined], axis=1).replace(
        [np.inf, -np.inf], 0.0
    ).fillna(0.0)


def dedup_against_edge_features(joined_df: pd.DataFrame, edge_columns: list[str]) -> pd.DataFrame:
    result = joined_df.copy()
    edge_set = set(edge_columns)
    drop_cols: list[str] = []
    aliases = {
        "src_fan_out_ratio": "source_fan_out",
    }
    for column in result.columns:
        if not (column.startswith("src_") or column.startswith("dst_")):
            continue
        base = column.removeprefix("src_").removeprefix("dst_")
        candidates = [base, aliases.get(column, "")]
        for edge_col in candidates:
            if edge_col in edge_set and edge_col in result.columns:
                left = result[column].to_numpy(dtype=float)
                right = result[edge_col].to_numpy(dtype=float)
                if np.allclose(left, right, equal_nan=True):
                    drop_cols.append(column)
                    break
    return result.drop(columns=sorted(set(drop_cols)))
