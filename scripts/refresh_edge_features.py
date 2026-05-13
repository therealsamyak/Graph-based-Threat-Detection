"""Refresh cached edge features from graph_edges.csv."""

from __future__ import annotations

import argparse
import logging
import shutil
import sys
import time
from pathlib import Path

import igraph as ig
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.features.edge import extract_edge_features  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("refresh_edge_features")

EDGE_ATTRS = [
    "auth_type", "logon_type", "auth_orientation", "success",
    "time", "weight", "first_time", "last_time", "protocol",
    "src_port", "dst_port", "pkt_count", "byte_count", "duration", "type",
]


def _build_graph(edges_df: pd.DataFrame) -> ig.Graph:
    names = pd.unique(pd.concat([edges_df["src"], edges_df["dst"]], ignore_index=True).astype(str))
    name_to_idx = {n: i for i, n in enumerate(names)}
    g = ig.Graph(directed=True)
    g.add_vertices(len(names))
    g.vs["name"] = list(names)

    src_idx = edges_df["src"].astype(str).map(name_to_idx).values
    dst_idx = edges_df["dst"].astype(str).map(name_to_idx).values
    g.add_edges(list(zip(src_idx.tolist(), dst_idx.tolist())))

    for attr in EDGE_ATTRS:
        if attr in edges_df.columns:
            values = edges_df[attr].tolist()
            g.es[attr] = values
    return g


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True,
                        help="Existing combined run dir (must contain graph_edges.csv).")
    parser.add_argument("--output", type=Path, required=True,
                        help="Parent dir for refreshed run (combined/ created inside).")
    args = parser.parse_args()

    in_combined = args.input.resolve()
    in_run_root = in_combined.parent
    out_combined = (args.output / "combined").resolve()
    out_combined.mkdir(parents=True, exist_ok=True)

    edges_csv = in_combined / "graph_edges.csv"
    if not edges_csv.exists():
        logger.error(f"Missing: {edges_csv}")
        return 1

    logger.info(f"Loading {edges_csv}")
    edges_df = pd.read_csv(edges_csv, low_memory=False)
    logger.info(f"{len(edges_df):,} edges, {edges_df['src'].nunique() + edges_df['dst'].nunique():,} approx node references")

    t0 = time.time()
    g = _build_graph(edges_df)
    logger.info(f"Built igraph: {g.vcount():,} nodes, {g.ecount():,} edges in {time.time()-t0:.1f}s")

    t0 = time.time()
    edge_features = extract_edge_features(g)
    logger.info(f"Extracted edge features in {time.time()-t0:.1f}s; shape={edge_features.shape}")

    out_edge_features = out_combined / "edge_features.csv"
    edge_features.to_csv(out_edge_features, index=True)
    logger.info(f"Wrote {out_edge_features}")

    copied: list[str] = []
    for fname in [
        "graph_edges.csv", "graph_nodes.csv", "node_features.csv",
        "edge_scores.csv", "graph_features.json",
        "detected_redteam_pairs.json", "anomalous_paths.csv", "paths.csv",
    ]:
        src = in_combined / fname
        if src.exists():
            shutil.copy(src, out_combined / fname)
            copied.append(fname)
    logger.info(f"Copied {len(copied)} support files from input combined/: {copied}")

    redteam_src = in_run_root / "redteam"
    if redteam_src.exists():
        redteam_dst = args.output / "redteam"
        shutil.copytree(redteam_src, redteam_dst, dirs_exist_ok=True)
        logger.info(f"Copied redteam dir to {redteam_dst}")

    duplicates = []
    if "weight_norm" in edge_features.columns and "edge_rarity" in edge_features.columns:
        wn = edge_features["weight_norm"].to_numpy()
        er = edge_features["edge_rarity"].to_numpy()
        if np.allclose(wn, er):
            duplicates.append("weight_norm == edge_rarity")
    if "source_fan_out" in edge_features.columns and "src_out_degree" in edge_features.columns:
        sfo = edge_features["source_fan_out"].to_numpy()
        sod = edge_features["src_out_degree"].to_numpy()
        if np.allclose(sfo, sod):
            duplicates.append("source_fan_out == src_out_degree")
    if duplicates:
        for d in duplicates:
            logger.error(d)
    else:
        logger.info("No exact duplicate features detected")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
