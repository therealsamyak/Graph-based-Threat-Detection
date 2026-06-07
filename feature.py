"""Phase 1: Build graphs, extract features, run audits, save to shared cache."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.feature_audit import run_audit
from src.feature_audit.types import AuditConfig
from src.features import extract_all_features
from src.stages import build_variant_graph, load_redteam_data

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 1: build graphs, extract features, run feature audit, save to shared cache.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Max events to stream (for quick testing).",
    )
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=None,
        help="LANL dataset directory. Defaults to config value.",
    )
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--min-auc", type=float, default=0.0)
    parser.set_defaults(log1p=True)
    parser.add_argument(
        "--no-log1p",
        dest="log1p",
        action="store_false",
        help="Disable log1p transforms for skewed count features.",
    )
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None):
    args = _parse_args(argv)
    config = load_config()
    data_dir = str(args.data_dir) if args.data_dir else config.data.lanl_dir

    from src.cache import prepare_cache_dir, save_redteam, save_features, save_top_features
    from src.variants import get_all_descriptors

    # 1. Load redteam data
    rt, red_pairs, windows = load_redteam_data(data_dir, config.data.window_size)

    # 2. Prepare cache and save redteam
    cdir = prepare_cache_dir(args.sample)
    save_redteam(cdir, rt, red_pairs, windows)

    descriptors = get_all_descriptors()
    top_features_map: dict[str, list[str]] = {}

    # Permanent results directory
    feat_results_id = datetime.now().strftime("%Y%m%d_%H%M%S")
    feat_results_dir = Path("results") / "feature_audit" / feat_results_id

    # 3. For each variant: build graph, extract features, run audit, save top features
    for descriptor in descriptors:
        variant = descriptor.name
        top_n = 5 if variant == "combined" else 3
        logger.info(f"── Variant: {variant} (top_n={top_n}) ──")

        # Build graph (cached)
        g, build_time, total_events = build_variant_graph(
            data_dir, windows, config, variant=variant, max_events=args.sample,
        )

        # Extract features
        all_feat = extract_all_features(g, config=config.to_dict(), variant_name=variant)

        # Compute graph_edges for audit
        edge_rows = [
            {"src": g.vs[e.source]["name"], "dst": g.vs[e.target]["name"]}
            for e in g.es
        ]
        graph_edges_df = pd.DataFrame(edge_rows)

        # Save to cache
        save_features(
            cdir, variant,
            edge_features=all_feat["edge_features"],
            node_features=all_feat.get("node_features"),
            graph_features=all_feat.get("graph_features", {}),
            graph_edges=graph_edges_df,
        )

        # Run feature audit (load from cache, write to permanent results)
        variant_dir = cdir / variant
        variant_results_dir = feat_results_dir / variant
        audit_config = AuditConfig(
            holdout_frac=args.holdout_frac,
            min_auc=args.min_auc,
            log1p_features=AuditConfig().log1p_features if args.log1p else [],
            random_seed=args.seed,
        )
        report = run_audit(variant_dir, variant_results_dir, audit_config)

        # Extract top N features (skip duplicates)
        top_features = [r.feature for r in report.features[:top_n] if not r.is_duplicate_of]
        if not top_features:
            # Fallback: take top N regardless of duplicates
            top_features = [r.feature for r in report.features[:top_n]]

        save_top_features(cdir, variant, top_features, top_n)
        top_features_map[variant] = top_features

        # Print variant summary
        logger.info(f"  [{variant}] Top {len(top_features)} features: {top_features}")
        logger.info(f"  [{variant}] Graph: {g.vcount():,} nodes, {g.ecount():,} edges")
        logger.info(f"  [{variant}] Build time: {build_time:.1f}s, Events: {total_events:,}")

    # 4. Save combined summary and print overall results
    feat_results_dir.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": feat_results_id,
        "cache_dir": str(cdir),
        "sample": args.sample,
        "variants": {v: {"top_features": f} for v, f in top_features_map.items()},
    }
    (feat_results_dir / "summary.json").write_text(json.dumps(summary, indent=2))

    print("=" * 80)
    print("PHASE 1 COMPLETE: Data Preparation + Feature Audit")
    print("=" * 80)
    print(f"Cache: {cdir}")
    print(f"Feature audit results: {feat_results_dir}")
    for variant, feats in top_features_map.items():
        print(f"  [{variant}] Top features: {', '.join(feats)}")
    print(f"Run 'uv run main.py --sample {args.sample}' to score and detect.")


def main() -> None:
    run()


if __name__ == "__main__":
    main()
