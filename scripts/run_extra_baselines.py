"""Standalone comparison runner for ML baselines on cached LANL features.

Loads cached `edge_features.csv` + `graph_edges.csv` + redteam pairs from a
prior run directory, applies the same mask used by `lanl_baselines.py`, and
runs all 5 ML baselines (OCSVM, IF, LOF, EllipticEnvelope, PCA reconstruction)
on the same feature matrix. Outputs a comparison table to stdout and writes
JSON + Markdown to the run directory.

Does not modify the main pipeline. Reads cached files only.

Usage:
    uv run python scripts/run_extra_baselines.py results/20260502_165755/combined
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# allow running from repo root without install
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.baselines.extra_baselines import run_extra_baselines  # noqa: E402
from src.baselines.shared_baselines import run_baselines  # noqa: E402

LANL_FEATURE_COLUMNS = [
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("extra_baselines")


def load_features_and_labels(run_dir: Path) -> tuple[np.ndarray, np.ndarray, list[str]]:
    edge_features_path = run_dir / "edge_features.csv"
    graph_edges_path = run_dir / "graph_edges.csv"
    redteam_pairs_path = run_dir.parent / "redteam" / "redteam_pairs.json"

    for p in (edge_features_path, graph_edges_path, redteam_pairs_path):
        if not p.exists():
            raise FileNotFoundError(f"Missing required input: {p}")

    logger.info(f"Loading edge features from {edge_features_path}")
    ef = pd.read_csv(edge_features_path)
    logger.info(f"Loading graph edges from {graph_edges_path}")
    edges = pd.read_csv(graph_edges_path, usecols=["src", "dst"])
    if len(edges) != len(ef):
        raise ValueError(
            f"Row count mismatch: edge_features.csv has {len(ef)}, graph_edges.csv has {len(edges)}"
        )

    logger.info(f"Loading red-team pairs from {redteam_pairs_path}")
    with open(redteam_pairs_path) as f:
        rt_list = json.load(f)
    red_pairs: set[tuple[str, str]] = {(p["src"], p["dst"]) for p in rt_list}
    logger.info(f"Loaded {len(red_pairs):,} red-team pairs")

    available = [c for c in LANL_FEATURE_COLUMNS if c in ef.columns]
    if not available:
        raise ValueError("No tabular feature columns found in edge_features")

    is_self_loop = ef["is_self_loop"].values if "is_self_loop" in ef.columns else np.zeros(len(ef))
    is_user_edge = ef["is_user_edge"].values if "is_user_edge" in ef.columns else np.zeros(len(ef))
    mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

    pair_arr = list(zip(edges["src"].values, edges["dst"].values))
    labels = np.fromiter(
        (1.0 if pair in red_pairs else 0.0 for pair in pair_arr),
        dtype=np.float64,
        count=len(pair_arr),
    )

    features = ef[available].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)

    features_v = features[mask]
    labels_v = labels[mask]
    logger.info(
        f"After mask: {len(features_v):,} edges ({int(labels_v.sum()):,} red-team), "
        f"{len(available)} features: {available}"
    )
    return features_v, labels_v, available


def format_markdown_table(results: list[dict]) -> str:
    if not results:
        return "(no results)\n"
    cols = ["method", "auc", "f1", "recall", "precision", "fpr"]
    header = "| " + " | ".join(cols) + " |"
    sep = "|" + "|".join("---" for _ in cols) + "|"
    rows = ["| " + " | ".join(str(r.get(c, "")) for c in cols) + " |" for r in results]
    return "\n".join([header, sep, *rows]) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dir",
        type=Path,
        help="Path to a results/<timestamp>/<dataset_variant> directory (e.g. results/20260502_165755/combined)",
    )
    parser.add_argument(
        "--config",
        type=Path,
        default=None,
        help="Optional JSON config with 'baselines' overrides. Defaults applied otherwise.",
    )
    parser.add_argument(
        "--out-suffix",
        type=str,
        default="extra_baselines",
        help="Suffix for output files (default: extra_baselines)",
    )
    parser.add_argument(
        "--sample-size",
        type=int,
        default=None,
        help="If set, subsample benign edges to this many (all red-team edges kept).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for subsampling (default: 42)",
    )
    args = parser.parse_args()

    run_dir = args.run_dir.resolve()
    if not run_dir.is_dir():
        logger.error(f"Not a directory: {run_dir}")
        return 1

    cfg: dict = {}
    if args.config and args.config.exists():
        cfg = json.loads(args.config.read_text())
    cfg.setdefault("baselines", {})
    cfg["baselines"].setdefault("oneclass_svm", {"kernel": "rbf", "gamma": "scale", "nu": 0.1})
    cfg["baselines"].setdefault("isolation_forest", {"n_estimators": 100, "contamination": 0.05, "random_state": 42})
    cfg["baselines"].setdefault("lof", {"n_neighbors": 20, "contamination": 0.05})
    cfg["baselines"].setdefault("elliptic_envelope", {"contamination": 0.05, "random_state": 42})
    cfg["baselines"].setdefault("pca_reconstruction", {"n_components": 5, "contamination": 0.05, "random_state": 42})

    features, labels, feat_names = load_features_and_labels(run_dir)

    if args.sample_size is not None and args.sample_size < (labels == 0).sum():
        rng = np.random.default_rng(args.seed)
        red_idx = np.where(labels == 1)[0]
        ben_idx = np.where(labels == 0)[0]
        keep_ben = rng.choice(ben_idx, size=int(args.sample_size), replace=False)
        keep = np.concatenate([red_idx, keep_ben])
        rng.shuffle(keep)
        features = features[keep]
        labels = labels[keep]
        logger.info(
            f"Subsampled to {len(features):,} edges ({int(labels.sum()):,} red-team kept, "
            f"{int(args.sample_size):,} benign sampled, seed={args.seed})"
        )

    logger.info("Running shared baselines (OCSVM + IF)...")
    t0 = time.time()
    shared = run_baselines(features, labels, config=cfg)
    t_shared = time.time() - t0
    logger.info(f"Shared baselines done in {t_shared:.1f}s")

    logger.info("Running extra baselines (LOF + EllipticEnvelope + PCA)...")
    t0 = time.time()
    extra = run_extra_baselines(features, labels, config=cfg)
    t_extra = time.time() - t0
    logger.info(f"Extra baselines done in {t_extra:.1f}s")

    all_results = shared + extra
    all_results.sort(key=lambda r: r.get("auc", 0.0), reverse=True)

    out_json = run_dir / f"{args.out_suffix}.json"
    out_md = run_dir / f"{args.out_suffix}.md"

    payload = {
        "run_dir": str(run_dir),
        "n_edges_evaluated": int(len(labels)),
        "n_redteam": int(labels.sum()),
        "feature_columns": feat_names,
        "config": cfg["baselines"],
        "sample_size": args.sample_size,
        "seed": args.seed,
        "results": all_results,
        "elapsed_sec": {"shared": round(t_shared, 2), "extra": round(t_extra, 2)},
    }
    out_json.write_text(json.dumps(payload, indent=2))

    md = ["# Extra-baselines comparison\n"]
    md.append(f"- run dir: `{run_dir}`")
    md.append(f"- edges evaluated (after mask): **{len(labels):,}** ({int(labels.sum()):,} red-team)")
    md.append(f"- features: {', '.join(feat_names)}\n")
    md.append("## Results (sorted by AUC desc)\n")
    md.append(format_markdown_table(all_results))
    md.append(f"\n_Shared baselines: {t_shared:.1f}s · Extra baselines: {t_extra:.1f}s_\n")
    out_md.write_text("\n".join(md))

    logger.info(f"Wrote {out_json}")
    logger.info(f"Wrote {out_md}")
    print()
    print(format_markdown_table(all_results))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
