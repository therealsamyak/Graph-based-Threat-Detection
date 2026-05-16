"""Load cached feature matrices and detect duplicate feature columns."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from src.feature_audit.joiner import dedup_against_edge_features, join_node_features


METADATA_COLUMNS = {"is_self_loop", "is_user_edge", "edge_index", "Unnamed: 0"}


def _require(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Missing required input: {path}")


def load_feature_frame(run_dir: Path) -> tuple[pd.DataFrame, np.ndarray, list[str]]:
    edge_features_path = run_dir / "edge_features.csv"
    graph_edges_path = run_dir / "graph_edges.csv"
    redteam_pairs_path = run_dir.parent / "redteam" / "redteam_pairs.json"

    for path in (edge_features_path, graph_edges_path, redteam_pairs_path):
        _require(path)

    edge_df = pd.read_csv(edge_features_path)
    edges = pd.read_csv(graph_edges_path, usecols=["src", "dst"])
    if len(edges) != len(edge_df):
        raise ValueError(
            f"Row count mismatch: edge_features.csv has {len(edge_df)}, graph_edges.csv has {len(edges)}"
        )

    with open(redteam_pairs_path) as f:
        redteam_pairs = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}

    is_self_loop = edge_df["is_self_loop"].values if "is_self_loop" in edge_df else np.zeros(len(edge_df))
    is_user_edge = edge_df["is_user_edge"].values if "is_user_edge" in edge_df else np.zeros(len(edge_df))
    mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

    labels = np.fromiter(
        (
            (src, dst) in redteam_pairs
            for src, dst in zip(edges["src"].astype(str).values, edges["dst"].astype(str).values)
        ),
        dtype=np.float64,
        count=len(edges),
    )
    joined = join_node_features(edge_df, graph_edges_path, run_dir / "node_features.csv")
    joined = dedup_against_edge_features(joined, list(edge_df.columns))
    columns = [c for c in joined.select_dtypes(include=[np.number]).columns if c not in METADATA_COLUMNS]
    if not columns:
        raise ValueError("No numeric feature columns found in cached features")

    features = joined.loc[mask, columns].reset_index(drop=True)
    features = features.replace([np.inf, -np.inf], 0.0).fillna(0.0)
    return features, labels[mask], columns


def load_features(run_dir: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    features, labels, columns = load_feature_frame(run_dir)
    return features.to_numpy(dtype=np.float64), labels, columns


def detect_duplicates(
    X: np.ndarray, columns: list[str], threshold: float = 0.999
) -> list[tuple[str, str]]:
    if X.shape[1] != len(columns):
        raise ValueError("Column count does not match feature matrix width")
    if X.shape[1] < 2:
        return []

    pairs: list[tuple[str, str]] = []
    seen_exact: dict[bytes, int] = {}
    exact_duplicates: set[int] = set()
    for i in range(X.shape[1]):
        column_key = np.ascontiguousarray(X[:, i]).tobytes()
        original = seen_exact.get(column_key)
        if original is None:
            seen_exact[column_key] = i
            continue
        pairs.append((columns[original], columns[i]))
        exact_duplicates.add(i)

    stds = np.std(X, axis=0)
    candidate_idx = [i for i in range(X.shape[1]) if i not in exact_duplicates]
    for left_pos, i in enumerate(candidate_idx):
        if stds[i] == 0.0:
            continue
        xi = X[:, i]
        for j in candidate_idx[left_pos + 1 :]:
            if stds[j] == 0.0:
                continue
            corr = float(np.corrcoef(xi, X[:, j])[0, 1])
            if abs(corr) > threshold:
                pairs.append((columns[i], columns[j]))
    return pairs

