"""Standalone feature audit runner for cached graph pipeline outputs."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.feature_audit import run_audit  # noqa: E402
from src.feature_audit.types import AuditConfig  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit cached edge/node features with held-out AUC.")
    parser.add_argument("run_dir", type=Path, help="Run directory containing combined cached CSV files")
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--min-auc", type=float, default=0.7)
    parser.add_argument("--log1p", dest="log1p", action="store_true", default=True)
    parser.add_argument("--no-log1p", dest="log1p", action="store_false")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log1p_features = AuditConfig().log1p_features if args.log1p else []
    config = AuditConfig(
        holdout_frac=args.holdout_frac,
        min_auc=args.min_auc,
        log1p_features=log1p_features,
        random_seed=args.seed,
    )
    output_dir = args.output_dir or args.run_dir
    try:
        report = run_audit(args.run_dir, config)
        output_dir.mkdir(parents=True, exist_ok=True)
        json_path = output_dir / "feature_audit_results.json"
        json_path.write_text(json.dumps(report.to_dict(), indent=2))
    except (FileNotFoundError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1

    print("Feature Audit Summary")
    print(f"Selected features ({len(report.selected_features)}): {', '.join(report.selected_features)}")
    print("Top features:")
    for result in report.features[:10]:
        marker = "*" if result.selected else " "
        print(f"{marker} {result.feature:30s} AUC={result.auc:.4f}")
    print(f"JSON: {json_path}")
    print(f"Markdown: {args.run_dir / 'feature_audit_results.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
