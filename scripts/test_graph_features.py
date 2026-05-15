"""Sweep quick-win graph features and report eval-AUC delta over LR baseline.

For each candidate graph feature (or feature group), we:
  1. Compute it on the full graph reconstructed from graph_edges.csv
  2. Apply the same self-loop / user-edge mask the audit/loader uses
  3. Add the new column(s) on top of the 5-feature LR baseline
  4. Fit logistic regression on the calibration half, evaluate on the held-out half
  5. Report eval AUC and the delta vs LR-on-5-features-alone

Output: results/<timestamp>/graph_features_test/graph_features_test.json
and a brief stdout summary.

Usage:
    uv run python scripts/test_graph_features.py \
        --run-dir results/20260515_002159/combined \
        [--attacker-host C17693]
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import igraph as ig
import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.feature_audit.loader import load_feature_frame  # noqa: E402
from src.feature_audit.scorer import stratified_split  # noqa: E402
from src.optimization.optimizer import RANK_TRANSFORM_FEATURES  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("test_graph_features")

BASE_FEATURES = [
    "is_ntlm",
    "source_fan_out",
    "dst_in_degree",
    "is_network_logon",
    "dst_fan_out_ratio",
]

EDGE_ATTRS = [
    "auth_type", "logon_type", "auth_orientation", "success",
    "time", "weight", "first_time", "last_time", "protocol",
    "src_port", "dst_port", "pkt_count", "byte_count", "duration", "type",
]


def _build_graph(edges_df: pd.DataFrame) -> tuple[ig.Graph, dict[str, int], np.ndarray, np.ndarray]:
    names = pd.unique(pd.concat([edges_df["src"], edges_df["dst"]], ignore_index=True).astype(str))
    name_to_idx = {n: i for i, n in enumerate(names)}
    g = ig.Graph(directed=True)
    g.add_vertices(len(names))
    g.vs["name"] = list(names)
    src_idx = edges_df["src"].astype(str).map(name_to_idx).to_numpy()
    dst_idx = edges_df["dst"].astype(str).map(name_to_idx).to_numpy()
    g.add_edges(list(zip(src_idx.tolist(), dst_idx.tolist())))
    for attr in EDGE_ATTRS:
        if attr in edges_df.columns:
            g.es[attr] = edges_df[attr].tolist()
    return g, name_to_idx, src_idx.astype(np.int64), dst_idx.astype(np.int64)


def _compute_quick_win_features(
    g: ig.Graph,
    src_idx: np.ndarray,
    dst_idx: np.ndarray,
    attacker_name: str | None,
    name_to_idx: dict[str, int],
) -> dict[str, dict[str, np.ndarray]]:
    """Return {group_name: {col_name: per-edge ndarray}} for each quick-win group."""
    groups: dict[str, dict[str, np.ndarray]] = {}

    # A) PageRank (standard, directed)
    t0 = time.time()
    pr = np.array(g.pagerank(directed=True, weights=None), dtype=float)
    logger.info(f"PageRank: {time.time()-t0:.1f}s")
    groups["pagerank"] = {
        "src_pagerank": pr[src_idx],
        "dst_pagerank": pr[dst_idx],
    }

    # B) Personalized PageRank from known attacker (if provided)
    if attacker_name and attacker_name in name_to_idx:
        t0 = time.time()
        ppr = np.array(
            g.personalized_pagerank(
                directed=True, weights=None, reset_vertices=[name_to_idx[attacker_name]]
            ),
            dtype=float,
        )
        logger.info(f"Personalized PageRank from {attacker_name}: {time.time()-t0:.1f}s")
        groups["personalized_pagerank"] = {
            "src_ppr_attacker": ppr[src_idx],
            "dst_ppr_attacker": ppr[dst_idx],
        }
    else:
        logger.warning(f"Skipping personalized PageRank (attacker {attacker_name!r} not in graph)")

    # C) k-core decomposition (undirected coreness)
    t0 = time.time()
    g_undir = g.as_undirected(mode="collapse")
    coreness = np.array(g_undir.coreness(), dtype=float)
    logger.info(f"k-core: {time.time()-t0:.1f}s")
    groups["kcore"] = {
        "src_kcore": coreness[src_idx],
        "dst_kcore": coreness[dst_idx],
    }

    # D) Community detection (Louvain on undirected)
    t0 = time.time()
    communities = g_undir.community_multilevel()
    comm_membership = np.array(communities.membership, dtype=np.int64)
    comm_size = np.array(
        [len(communities.subgraph(i).vs) for i in range(len(communities))],
        dtype=float,
    )
    logger.info(f"Louvain community: {time.time()-t0:.1f}s ({len(communities)} communities)")
    src_comm = comm_membership[src_idx]
    dst_comm = comm_membership[dst_idx]
    groups["community"] = {
        "cross_community": (src_comm != dst_comm).astype(float),
        "src_community_size": comm_size[src_comm],
        "dst_community_size": comm_size[dst_comm],
    }

    # E) Similarity (Jaccard + Adamic-Adar on undirected, for edge endpoints)
    t0 = time.time()
    pairs = list(zip(src_idx.tolist(), dst_idx.tolist()))
    jaccard = np.array(g_undir.similarity_jaccard(pairs=pairs, mode="all"), dtype=float)
    aa = _adamic_adar_per_edge(g_undir, src_idx, dst_idx)
    logger.info(f"Jaccard + Adamic-Adar: {time.time()-t0:.1f}s")
    groups["similarity"] = {
        "jaccard": jaccard,
        "adamic_adar": aa,
    }

    return groups


def _adamic_adar_per_edge(g: ig.Graph, src_idx: np.ndarray, dst_idx: np.ndarray) -> np.ndarray:
    """AA(u, v) = sum_{w in N(u) cap N(v)} 1 / log(deg(w))."""
    deg = np.array(g.degree(), dtype=float)
    log_deg_safe = np.where(deg > 1.0, np.log(deg), 0.0)
    inv = np.where(log_deg_safe > 0, 1.0 / log_deg_safe, 0.0)
    neighbor_sets = [set(g.neighbors(v)) for v in range(g.vcount())]
    out = np.zeros(len(src_idx), dtype=float)
    for i, (s, d) in enumerate(zip(src_idx, dst_idx)):
        if s == d:
            continue
        common = neighbor_sets[int(s)] & neighbor_sets[int(d)]
        if not common:
            continue
        out[i] = sum(inv[w] for w in common)
    return out


def _transform_features(features_df: pd.DataFrame, columns: list[str]) -> np.ndarray:
    cols: list[np.ndarray] = []
    for name in columns:
        col = features_df[name].to_numpy(dtype=float, copy=True)
        if name in RANK_TRANSFORM_FEATURES:
            col = pd.Series(col).rank(pct=True).to_numpy()
        cols.append(col)
    return np.column_stack(cols)


def _evaluate(
    X: np.ndarray, y: np.ndarray, cal_idx: np.ndarray, eval_idx: np.ndarray, seed: int
) -> tuple[float, float]:
    scaler = StandardScaler().fit(X[cal_idx])
    Xc = scaler.transform(X[cal_idx])
    Xe = scaler.transform(X[eval_idx])
    lr = LogisticRegression(
        class_weight="balanced", max_iter=2000, random_state=seed, solver="liblinear"
    )
    lr.fit(Xc, y[cal_idx])
    cal_auc = float(roc_auc_score(y[cal_idx], lr.predict_proba(Xc)[:, 1]))
    eval_auc = float(roc_auc_score(y[eval_idx], lr.predict_proba(Xe)[:, 1]))
    return cal_auc, eval_auc


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--attacker-host", type=str, default="C17693")
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=None)
    args = parser.parse_args()

    logger.info(f"Loading features from {args.run_dir}")
    features_df, labels, available_cols = load_feature_frame(args.run_dir)
    missing = [f for f in BASE_FEATURES if f not in features_df.columns]
    if missing:
        logger.error(f"Base features missing: {missing}")
        return 1

    edges_csv = args.run_dir / "graph_edges.csv"
    logger.info(f"Loading {edges_csv}")
    edges_df = pd.read_csv(edges_csv, low_memory=False)
    if len(edges_df) != len(features_df.index) and "is_self_loop" not in features_df.columns:
        # features_df is post-mask; we need a pre-mask alignment via edge index
        pass
    # The loader applies the (is_self_loop == 0) & (is_user_edge == 0) mask to
    # both rows and labels. We need the same mask to align graph-derived
    # per-edge features. Re-derive the mask from the raw edge_features.csv.
    ef_raw = pd.read_csv(args.run_dir / "edge_features.csv")
    if len(ef_raw) != len(edges_df):
        logger.error(f"Edge CSV row mismatch: {len(ef_raw)} vs {len(edges_df)}")
        return 1
    mask = (ef_raw["is_self_loop"].values == 0.0) & (ef_raw["is_user_edge"].values == 0.0)
    logger.info(f"Mask keeps {int(mask.sum()):,} / {len(mask):,} edges")

    logger.info("Building igraph...")
    t0 = time.time()
    g, name_to_idx, src_idx_all, dst_idx_all = _build_graph(edges_df)
    logger.info(f"Built graph: {g.vcount():,} nodes, {g.ecount():,} edges in {time.time()-t0:.1f}s")

    logger.info("Computing quick-win graph features...")
    groups = _compute_quick_win_features(g, src_idx_all, dst_idx_all, args.attacker_host, name_to_idx)

    # Apply mask to graph features
    masked_groups: dict[str, dict[str, np.ndarray]] = {}
    for gname, cols in groups.items():
        masked_groups[gname] = {col_name: arr[mask] for col_name, arr in cols.items()}

    # Verify alignment
    n_after_mask = len(features_df)
    for gname, cols in masked_groups.items():
        for col_name, arr in cols.items():
            if len(arr) != n_after_mask:
                logger.error(f"Length mismatch: {gname}/{col_name} {len(arr)} vs features_df {n_after_mask}")
                return 1

    # Base evaluation
    X_base = _transform_features(features_df, BASE_FEATURES)
    cal_idx, eval_idx = stratified_split(X_base, labels, args.holdout_frac, args.seed)
    logger.info(
        f"Stratified split: cal {len(cal_idx):,} ({int(labels[cal_idx].sum())} red-team), "
        f"eval {len(eval_idx):,} ({int(labels[eval_idx].sum())} red-team)"
    )

    base_cal_auc, base_eval_auc = _evaluate(X_base, labels, cal_idx, eval_idx, args.seed)
    logger.info(f"BASE (5 features): cal AUC {base_cal_auc:.6f}, eval AUC {base_eval_auc:.6f}")

    results: list[dict] = [{
        "name": "base_5_features",
        "added_columns": [],
        "n_features": 5,
        "cal_auc": base_cal_auc,
        "eval_auc": base_eval_auc,
        "eval_auc_delta_vs_base": 0.0,
    }]

    # Evaluate each group separately
    for gname, cols in masked_groups.items():
        added_cols = list(cols.keys())
        added_mat = np.column_stack([cols[c] for c in added_cols])
        X_combined = np.column_stack([X_base, added_mat])
        cal_auc, eval_auc = _evaluate(X_combined, labels, cal_idx, eval_idx, args.seed)
        delta = eval_auc - base_eval_auc
        logger.info(
            f"GROUP {gname}: +{len(added_cols)} cols ({', '.join(added_cols)}) "
            f"-> cal {cal_auc:.6f}, eval {eval_auc:.6f}, Δeval {delta:+.6f}"
        )
        results.append({
            "name": f"base_plus_{gname}",
            "added_columns": added_cols,
            "n_features": 5 + len(added_cols),
            "cal_auc": cal_auc,
            "eval_auc": eval_auc,
            "eval_auc_delta_vs_base": delta,
        })

    # Evaluate ALL groups stacked
    all_added_cols: list[str] = []
    all_added_arrays: list[np.ndarray] = []
    for gname, cols in masked_groups.items():
        for col_name, arr in cols.items():
            all_added_cols.append(f"{gname}.{col_name}")
            all_added_arrays.append(arr)
    if all_added_arrays:
        added_mat = np.column_stack(all_added_arrays)
        X_combined = np.column_stack([X_base, added_mat])
        cal_auc, eval_auc = _evaluate(X_combined, labels, cal_idx, eval_idx, args.seed)
        delta = eval_auc - base_eval_auc
        logger.info(
            f"ALL combined ({len(all_added_cols)} added): cal {cal_auc:.6f}, "
            f"eval {eval_auc:.6f}, Δeval {delta:+.6f}"
        )
        results.append({
            "name": "base_plus_all_quick_wins",
            "added_columns": all_added_cols,
            "n_features": 5 + len(all_added_cols),
            "cal_auc": cal_auc,
            "eval_auc": eval_auc,
            "eval_auc_delta_vs_base": delta,
        })

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_run_dir": str(args.run_dir.resolve()),
        "attacker_host": args.attacker_host,
        "holdout_frac": args.holdout_frac,
        "seed": args.seed,
        "n_calibration": int(len(cal_idx)),
        "n_eval": int(len(eval_idx)),
        "results": results,
    }

    if args.output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = REPO_ROOT / "results" / ts / "graph_features_test"
    else:
        out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "graph_features_test.json"
    out_path.write_text(json.dumps(payload, indent=2))
    logger.info(f"Wrote {out_path}")

    # Brief summary
    print("\nQuick-win results (eval AUC):")
    print(f"  {'name':40} {'cal AUC':>10} {'eval AUC':>10} {'Δ vs base':>10}")
    for r in results:
        print(f"  {r['name']:40} {r['cal_auc']:>10.6f} {r['eval_auc']:>10.6f} {r['eval_auc_delta_vs_base']:>+10.6f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
