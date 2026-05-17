"""Evaluation suite orchestrator for held-out analysis runs."""

from __future__ import annotations

import argparse
import csv
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from src.eval.holdout_optimizer import run_holdout_optimization
from src.eval.tabular_graph_ablation import run_tabular_graph_ablation
from src.eval.graph_feature_sweep import run_graph_feature_sweep

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def _latest_combined_run(results_dir: Path) -> Path:
    # Search two levels deep: results/<run_id>/combined/ or results/<run_id>/<dataset>/combined/
    candidates = []
    for run_dir in results_dir.iterdir():
        if not run_dir.is_dir():
            continue
        # Direct: results/<run_id>/combined/
        combined = run_dir / "combined"
        if combined.is_dir():
            candidates.append(combined)
        # Nested: results/<run_id>/<dataset>/combined/
        for sub in run_dir.iterdir():
            if sub.is_dir():
                combined = sub / "combined"
                if combined.is_dir():
                    candidates.append(combined)

    candidates.sort(key=lambda p: p.parent.name, reverse=True)
    for candidate in candidates:
        if (candidate / "edge_features.csv").exists() and (candidate / "graph_edges.csv").exists():
            return candidate
    raise FileNotFoundError(f"No cached combined run found under {results_dir}")


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run held-out evaluation analyses on cached graph pipeline features.",
    )
    parser.add_argument("--run-dir", type=Path, default=None, help="Cached run dir. Defaults to latest results/*/combined.")
    parser.add_argument("--results-dir", type=Path, default=Path("results"), help="Directory to search for cached runs.")
    parser.add_argument("--output-root", type=Path, default=Path("analysis_results"), help="Root directory for eval outputs.")
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--attacker-host", type=str, default="C17693", help="Attacker host for graph feature sweep.")
    parser.add_argument("--features", type=str, default=None, help="Comma-separated features for holdout. Defaults to DEFAULT_FEATURES.")

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("holdout", help="Held-out weight optimization evaluation")
    sub.add_parser("ablation", help="Pure-tabular vs graph-derived feature ablation")
    sub.add_parser("sweep", help="Quick-win graph feature sweep")

    return parser.parse_args(argv)


def _write_summary(output_dir: Path, eval_results: dict, run_id: str, run_dir: Path, holdout_frac: float, seed: int) -> None:
    """Write summary.json and eval_summary.csv to output_dir."""
    summary = {
        "eval_run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_run_dir": str(run_dir.resolve()),
        "holdout_frac": holdout_frac,
        "seed": seed,
        "evals": eval_results,
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2))
    logger.info(f"Wrote {output_dir / 'summary.json'}")

    rows = []
    for eval_type, payload in eval_results.items():
        row = {
            "eval_type": eval_type,
            "eval_run_id": run_id,
            "n_calibration": payload.get("n_calibration"),
            "n_eval": payload.get("n_eval"),
        }
        if eval_type == "holdout":
            opt = payload.get("optimizer", {})
            lr = payload.get("logistic_regression", {})
            row["cal_auc"] = opt.get("auc_calibration")
            row["eval_auc"] = opt.get("auc_eval")
            row["lr_cal_auc"] = lr.get("auc_calibration")
            row["lr_eval_auc"] = lr.get("auc_eval")
            row["n_features"] = len(payload.get("features", []))
            row["delta_optimizer_vs_lr"] = payload.get("delta_eval_auc_optimizer_minus_lr")
        elif eval_type == "ablation":
            results = payload.get("results", [])
            row["cal_auc"] = None
            row["eval_auc"] = None
            row["ablation_results"] = json.dumps([
                {"name": r["name"], "n_features": r["n_features"], "cal_auc": r["cal_auc"], "eval_auc": r["eval_auc"]}
                for r in results
            ])
            row["delta_graph_to_tabular"] = payload.get("delta_adding_graph_to_tabular")
            row["delta_tabular_to_graph"] = payload.get("delta_adding_tabular_to_graph")
        elif eval_type == "sweep":
            results = payload.get("results", [])
            base = next((r for r in results if r["name"] == "base_5_features"), {})
            all_combined = next((r for r in results if r["name"] == "base_plus_all_quick_wins"), {})
            row["cal_auc"] = base.get("cal_auc")
            row["eval_auc"] = base.get("eval_auc")
            row["best_delta"] = max((r.get("eval_auc_delta_vs_base", 0) for r in results), default=0)
            row["all_combined_delta"] = all_combined.get("eval_auc_delta_vs_base")
            row["n_sweep_groups"] = len([r for r in results if r["name"] != "base_5_features"])
        rows.append(row)

    csv_path = output_dir / "eval_summary.csv"
    if rows:
        all_keys: set[str] = set()
        for row in rows:
            all_keys.update(row.keys())
        fieldnames = sorted(all_keys)
        with open(csv_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)
        logger.info(f"Wrote {csv_path}")


def main() -> None:
    args = _parse_args()
    run_dir = args.run_dir or _latest_combined_run(args.results_dir)
    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    output_dir = args.output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)
    logger.info(f"Eval output: {output_dir}")

    command = args.command  # None = run all
    eval_results: dict = {}

    if command in (None, "holdout"):
        feature_list = [f.strip() for f in args.features.split(",") if f.strip()] if args.features else None
        logger.info("Running holdout optimization...")
        eval_results["holdout"] = run_holdout_optimization(
            run_dir, feature_list=feature_list,
            holdout_frac=args.holdout_frac, seed=args.seed,
            output_dir=output_dir,
        )

    if command in (None, "ablation"):
        logger.info("Running tabular vs graph ablation...")
        eval_results["ablation"] = run_tabular_graph_ablation(
            run_dir, holdout_frac=args.holdout_frac,
            seed=args.seed, output_dir=output_dir,
        )

    if command in (None, "sweep"):
        logger.info("Running graph feature sweep...")
        eval_results["sweep"] = run_graph_feature_sweep(
            run_dir, attacker_host=args.attacker_host,
            holdout_frac=args.holdout_frac, seed=args.seed,
            output_dir=output_dir,
        )

    _write_summary(output_dir, eval_results, run_id, run_dir, args.holdout_frac, args.seed)

    print(f"\nEval run complete: {output_dir}")
    print(f"  summary.json: {output_dir / 'summary.json'}")
    print(f"  eval_summary.csv: {output_dir / 'eval_summary.csv'}")


if __name__ == "__main__":
    main()