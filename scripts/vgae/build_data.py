"""Build a PyG Data object from cached pipeline outputs.

Reads:
  <run_dir>/graph_edges.csv         (one row per directed edge)
  <run_dir>/node_features.csv       (one row per node, with numeric features)
  <run_dir>/../redteam/redteam_pairs.json  (ground-truth red-team pairs)

Produces a torch_geometric.data.Data object with:
  data.x          (N, F) float node features (StandardScaler-fit on benign-only)
  data.edge_index (2, E) long source/destination node indices
  data.y          (E,)   binary per-edge red-team labels (eval-only; not used at training time)
  data.mask       (E,)   bool, True for edges to score (not self-loops, not user-edges)
  data.weight     (E,)   float edge weights (informational; not used by VGAE)

The Data object is cached as <output_path>.pt for fast reload.

Usage (called from train_vgae.py, or standalone):
    .venv-vgae/bin/python scripts/vgae/build_data.py \
        --run-dir results/20260515_002159/combined \
        --output  .venv-vgae/cache/vgae_data.pt
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch_geometric.data import Data

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("build_data")

REPO_ROOT = Path(__file__).resolve().parents[2]


def _load_node_features(node_features_csv: Path, node_to_idx: dict[str, int]) -> tuple[np.ndarray, list[str]]:
    df = pd.read_csv(node_features_csv)
    if "node" in df.columns:
        df = df.set_index("node")
    df.index = df.index.astype(str)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if not numeric_cols:
        raise ValueError("No numeric columns in node_features.csv")
    df = df[numeric_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    n_nodes = len(node_to_idx)
    out = np.zeros((n_nodes, len(numeric_cols)), dtype=np.float64)
    found = 0
    for name, idx in node_to_idx.items():
        if name in df.index:
            out[idx] = df.loc[name].to_numpy(dtype=np.float64)
            found += 1
    logger.info(f"Node features matched for {found:,} / {n_nodes:,} nodes ({len(numeric_cols)} feature columns)")
    return out, numeric_cols


def build_data(run_dir: Path) -> Data:
    edges_csv = run_dir / "graph_edges.csv"
    node_features_csv = run_dir / "node_features.csv"
    edge_features_csv = run_dir / "edge_features.csv"
    redteam_pairs_path = run_dir.parent / "redteam" / "redteam_pairs.json"

    for path in (edges_csv, node_features_csv, edge_features_csv, redteam_pairs_path):
        if not path.exists():
            raise FileNotFoundError(f"Missing required input: {path}")

    logger.info(f"Loading {edges_csv}")
    edges_df = pd.read_csv(edges_csv, low_memory=False, usecols=["src", "dst", "weight"])
    logger.info(f"Loading {edge_features_csv} (for is_self_loop / is_user_edge mask)")
    ef = pd.read_csv(edge_features_csv, usecols=["is_self_loop", "is_user_edge"])
    if len(ef) != len(edges_df):
        raise ValueError(f"Row count mismatch: edge_features.csv ({len(ef)}) vs graph_edges.csv ({len(edges_df)})")

    names = pd.unique(pd.concat([edges_df["src"], edges_df["dst"]], ignore_index=True).astype(str))
    node_to_idx = {n: i for i, n in enumerate(names)}
    n_nodes = len(names)
    n_edges = len(edges_df)
    logger.info(f"Graph: {n_nodes:,} nodes, {n_edges:,} edges")

    src_idx = edges_df["src"].astype(str).map(node_to_idx).to_numpy(dtype=np.int64)
    dst_idx = edges_df["dst"].astype(str).map(node_to_idx).to_numpy(dtype=np.int64)
    weights = edges_df["weight"].to_numpy(dtype=np.float64)

    logger.info(f"Loading red-team pairs from {redteam_pairs_path}")
    with open(redteam_pairs_path) as f:
        rt = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}
    labels = np.fromiter(
        (
            (s, d) in rt
            for s, d in zip(edges_df["src"].astype(str).values, edges_df["dst"].astype(str).values)
        ),
        dtype=np.int64,
        count=n_edges,
    )

    mask = (ef["is_self_loop"].to_numpy() == 0.0) & (ef["is_user_edge"].to_numpy() == 0.0)
    logger.info(
        f"Mask keeps {int(mask.sum()):,} / {n_edges:,} edges; "
        f"{int(labels[mask].sum())} red-team in masked set"
    )

    node_x_raw, node_feat_names = _load_node_features(node_features_csv, node_to_idx)

    benign_node_mask = np.ones(n_nodes, dtype=bool)
    redteam_node_ids = set()
    for s, d in rt:
        if s in node_to_idx:
            redteam_node_ids.add(node_to_idx[s])
    for nid in redteam_node_ids:
        benign_node_mask[nid] = False
    logger.info(
        f"Scaler fit on {int(benign_node_mask.sum()):,} benign nodes "
        f"({int((~benign_node_mask).sum()):,} red-team-source nodes excluded)"
    )
    scaler = StandardScaler().fit(node_x_raw[benign_node_mask])
    node_x = scaler.transform(node_x_raw).astype(np.float32)

    edge_index = torch.tensor(np.stack([src_idx, dst_idx], axis=0), dtype=torch.long)
    data = Data(
        x=torch.tensor(node_x, dtype=torch.float),
        edge_index=edge_index,
        y=torch.tensor(labels, dtype=torch.long),
    )
    data.mask = torch.tensor(mask, dtype=torch.bool)
    data.weight = torch.tensor(weights, dtype=torch.float)
    data.node_feat_names = node_feat_names
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="Where to cache the .pt file")
    args = parser.parse_args()

    args.output.parent.mkdir(parents=True, exist_ok=True)
    data = build_data(args.run_dir.resolve())
    torch.save(data, args.output)
    logger.info(f"Wrote {args.output}")
    logger.info(
        f"data.x shape={tuple(data.x.shape)} "
        f"data.edge_index shape={tuple(data.edge_index.shape)} "
        f"data.y sum={int(data.y.sum())} mask sum={int(data.mask.sum())}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
