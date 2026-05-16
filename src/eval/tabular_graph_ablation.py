"""Pure-tabular vs graph-derived feature ablation under held-out LR."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score
from sklearn.preprocessing import StandardScaler

from src.feature_audit.loader import load_feature_frame
from src.feature_audit.scorer import stratified_split

PURE_TABULAR = [
    "is_ntlm", "is_network_logon", "is_success_auth",
    "edge_rarity", "weight_norm",
    "protocol_rarity", "byte_per_packet",
    "duration_zscore", "is_unusual_dst_port",
]
GRAPH_DERIVED = [
    "src_out_degree", "src_in_degree", "src_total_degree",
    "dst_out_degree", "dst_in_degree", "dst_total_degree",
    "source_fan_out", "dst_fan_out_ratio",
    "src_burst_score", "dst_burst_score",
    "src_inter_arrival_mean", "src_inter_arrival_std",
    "dst_inter_arrival_mean", "dst_inter_arrival_std",
    "src_active_duration", "dst_active_duration",
    "dst_betweenness_centrality",
]


def _evaluate(features_df: pd.DataFrame, labels: np.ndarray, cols: list[str],
              cal_idx: np.ndarray, eval_idx: np.ndarray, seed: int) -> tuple[float, float]:
    X = features_df[cols].to_numpy(dtype=float)
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)
    scaler = StandardScaler().fit(X[cal_idx])
    Xc = scaler.transform(X[cal_idx])
    Xe = scaler.transform(X[eval_idx])
    lr = LogisticRegression(
        class_weight="balanced", max_iter=2000, random_state=seed, solver="liblinear"
    )
    lr.fit(Xc, labels[cal_idx])
    cal_auc = float(roc_auc_score(labels[cal_idx], lr.predict_proba(Xc)[:, 1]))
    eval_auc = float(roc_auc_score(labels[eval_idx], lr.predict_proba(Xe)[:, 1]))
    return cal_auc, eval_auc


def run_tabular_graph_ablation(
    run_dir: Path,
    holdout_frac: float = 0.5,
    seed: int = 42,
    output_dir: Path | None = None,
) -> dict:
    features_df, labels, _ = load_feature_frame(run_dir)
    tabular_avail = [c for c in PURE_TABULAR if c in features_df.columns]
    graph_avail = [c for c in GRAPH_DERIVED if c in features_df.columns]
    print(f"Pure-tabular features available: {len(tabular_avail)} of {len(PURE_TABULAR)}")
    print(f"Graph-derived features available: {len(graph_avail)} of {len(GRAPH_DERIVED)}")

    base_X = features_df[tabular_avail + graph_avail].to_numpy()
    cal_idx, eval_idx = stratified_split(base_X, labels, holdout_frac, seed)
    print(
        f"Stratified split: cal {len(cal_idx):,} ({int(labels[cal_idx].sum())} red-team), "
        f"eval {len(eval_idx):,} ({int(labels[eval_idx].sum())} red-team)"
    )

    cal_t, eval_t = _evaluate(features_df, labels, tabular_avail, cal_idx, eval_idx, seed)
    cal_g, eval_g = _evaluate(features_df, labels, graph_avail, cal_idx, eval_idx, seed)
    cal_c, eval_c = _evaluate(features_df, labels, tabular_avail + graph_avail, cal_idx, eval_idx, seed)

    results = [
        {"name": "pure_tabular_only", "columns": tabular_avail, "n_features": len(tabular_avail),
         "cal_auc": cal_t, "eval_auc": eval_t},
        {"name": "graph_derived_only", "columns": graph_avail, "n_features": len(graph_avail),
         "cal_auc": cal_g, "eval_auc": eval_g},
        {"name": "combined", "columns": tabular_avail + graph_avail,
         "n_features": len(tabular_avail) + len(graph_avail),
         "cal_auc": cal_c, "eval_auc": eval_c},
    ]
    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_run_dir": str(run_dir.resolve()),
        "holdout_frac": holdout_frac,
        "seed": seed,
        "n_calibration": int(len(cal_idx)),
        "n_eval": int(len(eval_idx)),
        "results": results,
        "delta_adding_graph_to_tabular": eval_c - eval_t,
        "delta_adding_tabular_to_graph": eval_c - eval_g,
    }

    print()
    print(f"{'feature set':25} n_feats  cal AUC   eval AUC")
    for r in results:
        print(f"  {r['name']:25} {r['n_features']:>5}    {r['cal_auc']:.6f}  {r['eval_auc']:.6f}")
    print()
    print(f"Δ eval AUC from adding graph to tabular: {payload['delta_adding_graph_to_tabular']:+.6f}")
    print(f"Δ eval AUC from adding tabular to graph: {payload['delta_adding_tabular_to_graph']:+.6f}")

    if output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = Path("analysis_results") / ts
        out_dir.mkdir(parents=True, exist_ok=True)
    else:
        out_dir = output_dir.resolve()
    out_path = out_dir / "tabular_vs_graph_ablation.json"
    out_path.write_text(json.dumps(payload, indent=2))
    print(f"\nWrote {out_path}")
    return payload
