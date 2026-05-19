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

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)


def _find_variants(results_dir: Path, variant: str | None = None) -> list[tuple[str, Path]]:
    valid_variants = {"combined", "auth_only", "flow_only"}
    run_dirs = []
    for run_dir in results_dir.iterdir():
        if not run_dir.is_dir() or run_dir.name == "pending":
            continue
        run_dirs.append(run_dir)
    run_dirs.sort(key=lambda d: d.name, reverse=True)
    if not run_dirs:
        raise FileNotFoundError(f"No run directories found under {results_dir}")
    latest_run = run_dirs[0]
    run_id = latest_run.name
    variants = []
    for variant_name in valid_variants:
        variant_path = latest_run / variant_name
        if variant_path.is_dir():
            variants.append((variant_name, variant_path))
        for dataset_dir in latest_run.iterdir():
            if dataset_dir.is_dir():
                variant_path = dataset_dir / variant_name
                if variant_path.is_dir():
                    variants.append((variant_name, variant_path))
    valid = []
    for variant_name, variant_path in variants:
        if (variant_path / "edge_features.csv").exists() and (
            variant_path / "graph_edges.csv"
        ).exists():
            valid.append((variant_name, variant_path))
    if variant is not None:
        found = {v for v, _ in valid}
        if variant not in found:
            raise FileNotFoundError(
                f"Variant '{variant}' not found in run {run_id}. Available: {found}"
            )
        valid = [(v, p) for v, p in valid if v == variant]
    return valid


def _warn_zero_variance(run_dir: Path, variant: str) -> None:
    """Warn about zero-variance features in edge_features.csv."""
    csv_path = run_dir / "edge_features.csv"
    if not csv_path.exists():
        return
    with open(csv_path, newline="") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    if not rows:
        return
    for col in reader.fieldnames or []:
        if col in ("src", "dst"):
            continue
        values = {row[col] for row in rows}
        if len(values) <= 1:
            logger.warning(
                f"Feature '{col}' has zero variance in {variant} variant. "
                "Eval results may be unreliable."
            )


def _parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Run held-out evaluation analyses on cached graph pipeline features.",
    )
    parser.add_argument(
        "--run-dir",
        type=Path,
        default=None,
        help="Cached run dir (or run_id root to evaluate all variants). Defaults to latest results/*/combined.",
    )
    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory to search for cached runs.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("analysis_results"),
        help="Root directory for eval outputs.",
    )
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--attacker-host",
        type=str,
        default="C17693",
        help="Attacker host for graph feature sweep.",
    )
    parser.add_argument(
        "--features",
        type=str,
        default=None,
        help="Comma-separated features for holdout. Defaults to DEFAULT_FEATURES.",
    )
    parser.add_argument(
        "--variant",
        type=str,
        default=None,
        choices=["combined", "auth_only", "flow_only"],
        help="Evaluate specific variant. Default: evaluate all found variants.",
    )

    sub = parser.add_subparsers(dest="command")
    sub.add_parser("holdout", help="Held-out weight optimization evaluation")
    sub.add_parser("ablation", help="Pure-tabular vs graph-derived feature ablation")
    sub.add_parser("sweep", help="Quick-win graph feature sweep")

    return parser.parse_args(argv)


def _write_summary(
    output_dir: Path,
    eval_results: dict,
    run_id: str,
    run_dir: Path,
    holdout_frac: float,
    seed: int,
    variant: str,
) -> None:
    """Write summary.json and eval_summary.csv to output_dir."""
    summary = {
        "eval_run_id": run_id,
        "variant": variant,
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
            "variant": variant,
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
            row["delta_optimizer_vs_lr"] = payload.get(
                "delta_eval_auc_optimizer_minus_lr"
            )
        elif eval_type == "ablation":
            results = payload.get("results", [])
            row["cal_auc"] = None
            row["eval_auc"] = None
            row["ablation_results"] = json.dumps(
                [
                    {
                        "name": r["name"],
                        "n_features": r["n_features"],
                        "cal_auc": r["cal_auc"],
                        "eval_auc": r["eval_auc"],
                    }
                    for r in results
                ]
            )
            row["delta_graph_to_tabular"] = payload.get("delta_adding_graph_to_tabular")
            row["delta_tabular_to_graph"] = payload.get("delta_adding_tabular_to_graph")
        elif eval_type == "sweep":
            results = payload.get("results", [])
            base = next((r for r in results if r["name"].startswith("base_")), {})
            all_combined = next(
                (r for r in results if r["name"] == "base_plus_all_quick_wins"), {}
            )
            row["cal_auc"] = base.get("cal_auc")
            row["eval_auc"] = base.get("eval_auc")
            row["best_delta"] = max(
                (r.get("eval_auc_delta_vs_base", 0) for r in results), default=0
            )
            row["all_combined_delta"] = all_combined.get("eval_auc_delta_vs_base")
            row["n_sweep_groups"] = len(
                [r for r in results if r["name"] != "base_5_features"]
            )
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

    valid_variants = {"combined", "auth_only", "flow_only"}
    variants_to_eval: list[tuple[str, Path]] = []

    if args.run_dir:
        run_dir_path = args.run_dir.resolve()
        run_dir_name = run_dir_path.name

        if run_dir_name in valid_variants:
            variants_to_eval = [(run_dir_name, run_dir_path)]
            logger.info(
                f"Detected variant dir via --run-dir: {run_dir_name} at {run_dir_path}"
            )
        else:
            if not run_dir_path.is_dir():
                raise FileNotFoundError(f"Run directory not found: {run_dir_path}")
            for vname in valid_variants:
                vpath = run_dir_path / vname
                if vpath.is_dir() and (vpath / "edge_features.csv").exists() and (vpath / "graph_edges.csv").exists():
                    variants_to_eval.append((vname, vpath))
                    continue
                for dataset_dir in run_dir_path.iterdir():
                    if dataset_dir.is_dir():
                        vpath = dataset_dir / vname
                        if vpath.is_dir() and (vpath / "edge_features.csv").exists() and (vpath / "graph_edges.csv").exists():
                            variants_to_eval.append((vname, vpath))
            if args.variant:
                variants_to_eval = [(v, p) for v, p in variants_to_eval if v == args.variant]
            if not variants_to_eval:
                raise FileNotFoundError(
                    f"No valid variants found in {run_dir_path}. "
                    f"Ensure the directory contains variant subdirectories "
                    f"(combined/, auth_only/, flow_only/) with edge_features.csv and graph_edges.csv."
                )
            logger.info(
                f"Discovered {len(variants_to_eval)} variant(s) from run_id root: {run_dir_path}"
            )
    else:
        try:
            variants_to_eval = _find_variants(args.results_dir, args.variant)
            logger.info(
                f"Auto-discovered {len(variants_to_eval)} variant(s) from latest run in {args.results_dir}"
            )
        except FileNotFoundError as e:
            raise FileNotFoundError(
                f"No valid runs found in {args.results_dir}. "
                f"Ensure results contain run directories with variant subdirectories "
                f"(combined/, auth_only/, flow_only/) with edge_features.csv and graph_edges.csv."
            ) from e

    if not variants_to_eval:
        raise FileNotFoundError("No variants to evaluate.")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    logger.info(f"Eval run ID: {run_id}")

    command = args.command  # None = run all
    variant_outputs: dict[str, Path] = {}

    for variant_name, variant_path in variants_to_eval:
        logger.info("=" * 60)
        logger.info(f"Evaluating variant: {variant_name}")
        logger.info(f"Eval input: {variant_path}")

        output_dir = args.output_root / run_id / variant_name
        output_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Eval output: {output_dir}")

        _warn_zero_variance(variant_path, variant_name)

        eval_results: dict = {}

        if command in (None, "holdout"):
            feature_list = (
                [f.strip() for f in args.features.split(",") if f.strip()]
                if args.features
                else None
            )
            logger.info("Running holdout optimization...")
            eval_results["holdout"] = run_holdout_optimization(
                variant_path,
                feature_list=feature_list,
                holdout_frac=args.holdout_frac,
                seed=args.seed,
                output_dir=output_dir,
            )

        if command in (None, "ablation"):
            logger.info("Running tabular vs graph ablation...")
            eval_results["ablation"] = run_tabular_graph_ablation(
                variant_path,
                holdout_frac=args.holdout_frac,
                seed=args.seed,
                output_dir=output_dir,
            )

        if command in (None, "sweep"):
            logger.info("Running graph feature sweep...")
            eval_results["sweep"] = run_graph_feature_sweep(
                variant_path,
                attacker_host=args.attacker_host,
                holdout_frac=args.holdout_frac,
                seed=args.seed,
                output_dir=output_dir,
            )

        _write_summary(
            output_dir, eval_results, run_id, variant_path, args.holdout_frac, args.seed, variant_name
        )

        variant_outputs[variant_name] = output_dir

    print(f"\nEval run complete: {args.output_root / run_id}")
    print(f"  Run ID: {run_id}")
    for variant_name, output_dir in variant_outputs.items():
        print(f"  Variant '{variant_name}':")
        print(f"    summary.json: {output_dir / 'summary.json'}")
        print(f"    eval_summary.csv: {output_dir / 'eval_summary.csv'}")


if __name__ == "__main__":
    main()
