"""Feature audit orchestrator for cached graph pipeline outputs."""

from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.feature_audit import run_audit
from src.feature_audit.types import AuditConfig

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def _latest_combined_run(results_dir: Path) -> Path:
    candidates = sorted(
        (path / "combined" for path in results_dir.iterdir() if path.is_dir()),
        key=lambda path: path.parent.name,
        reverse=True,
    )
    for candidate in candidates:
        if (candidate / "edge_features.csv").exists() and (candidate / "graph_edges.csv").exists():
            return candidate
    raise FileNotFoundError(f"No cached combined run found under {results_dir}")


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run held-out AUC feature audit on cached graph pipeline features."
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Cached run directory containing combined edge/node CSVs. Defaults to latest results/*/combined.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory to search for cached pipeline runs when --run-dir is omitted.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("feature_results"),
        help="Root directory for feature audit outputs.",
    )
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--min-auc", type=float, default=0.7)
    parser.add_argument("--log1p", dest="log1p", action="store_true", default=True)
    parser.add_argument("--no-log1p", dest="log1p", action="store_false")
    parser.add_argument("--seed", type=int, default=42)
    return parser.parse_args(argv)


def run(argv: list[str] | None = None):
    args = _parse_args(argv)
    run_dir = args.run_dir or _latest_combined_run(args.results_dir)
    audit_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / audit_id
    output_dir.mkdir(parents=True, exist_ok=True)

    log1p_features = AuditConfig().log1p_features if args.log1p else []
    config = AuditConfig(
        holdout_frac=args.holdout_frac,
        min_auc=args.min_auc,
        log1p_features=log1p_features,
        random_seed=args.seed,
    )

    logger.info("Feature audit input: %s", run_dir)
    logger.info("Feature audit output: %s", output_dir)
    report = run_audit(run_dir, output_dir, config)

    metadata = {
        "audit_id": audit_id,
        "input_run_dir": str(run_dir),
        "output_dir": str(output_dir),
        "selected_feature_count": len(report.selected_features),
    }
    (output_dir / "metadata.json").write_text(json.dumps(metadata, indent=2))

    print("Feature Audit Summary")
    print(f"Input: {run_dir}")
    print(f"Output: {output_dir}")
    print(f"Selected features ({len(report.selected_features)}): {', '.join(report.selected_features)}")
    print("Top features:")
    for result in report.features[:10]:
        marker = "*" if result.selected else " "
        print(f"{marker} {result.feature:30s} AUC={result.auc:.4f}")
    print(f"JSON: {output_dir / 'feature_audit_results.json'}")
    print(f"Markdown: {output_dir / 'Feature_Audit_Results.md'}")
    return report


def main() -> None:
    run()


if __name__ == "__main__":
    main()
