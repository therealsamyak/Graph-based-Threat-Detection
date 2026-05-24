"""Phase 2: Load cached features, score, detect, generate figures."""

from __future__ import annotations

import argparse
import io
import json
import logging
import time
from pathlib import Path

import pandas as pd

from src.config import load_config
from src.io import save_method_results, save_pipeline_config, save_redteam_data
from src.reporting import generate_comparison
from src.stages import build_variant_graph, load_redteam_data, _score_detect_graph
from src.types import PipelineConfig
from src.utils import compute_edge_pair_names

LOG_FMT = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

logging.basicConfig(
    level=logging.INFO,
    format=LOG_FMT,
)
logger = logging.getLogger(__name__)

_log_buffer = io.StringIO()
_buffer_handler = logging.StreamHandler(_log_buffer)
_buffer_handler.setLevel(logging.INFO)
_buffer_handler.setFormatter(logging.Formatter(LOG_FMT))
logging.getLogger().addHandler(_buffer_handler)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 2: load cached features, score, detect, generate figures.",
    )
    parser.add_argument(
        "--sample",
        type=int,
        default=None,
        help="Limit number of events per source for quick testing",
    )
    return parser.parse_args(argv)


def _print_summary(df: pd.DataFrame) -> None:
    if df.empty:
        print("\nNo results to display.")
        return

    base_cols = ["method", "dataset", "recall", "fpr", "f1", "auc", "latency", "throughput"]
    optional_cols = ["rt_pairs_in_graph", "anomalous_pairs", "threshold"]
    cols = [c for c in base_cols + optional_cols if c in df.columns]
    display_df = df[cols].copy()
    for c in ["recall", "fpr", "f1", "auc"]:
        if c in display_df.columns:
            display_df[c] = display_df[c].map(lambda v: f"{v:.4f}")
    if "latency" in display_df.columns:
        display_df["latency"] = display_df["latency"].map(lambda v: f"{v:.2f}s")
    if "throughput" in display_df.columns:
        display_df["throughput"] = display_df["throughput"].map(lambda v: f"{v:.0f}/s")

    print("\n" + "=" * 120)
    print(f"EXPERIMENT RESULTS SUMMARY ({len(df)} pipeline variants)")
    print("=" * 120)
    print(display_df.to_string(index=False))
    print("=" * 120 + "\n")


def run(argv: list[str] | None = None) -> pd.DataFrame:
    args = _parse_args(argv)
    config: PipelineConfig = load_config()

    from src.cache import (
        cache_dir,
        has_complete_cache,
        load_redteam,
        load_graph,
        load_features,
        load_top_features,
    )
    from src.variants import get_all_descriptors

    cdir = cache_dir(args.sample)
    using_cache = has_complete_cache(cdir)

    if using_cache:
        logger.info(f"Loading from cache: {cdir}")
        rt, red_pairs, windows = load_redteam(cdir)
    else:
        logger.info("Cache not found or incomplete, building from scratch...")
        data_dir = config.data.lanl_dir
        rt, red_pairs, windows = load_redteam_data(data_dir, config.data.window_size)

    descriptors = get_all_descriptors()

    # Generate run ID and set up output dirs (same as original pipeline)
    from src.pipeline import generate_run_id, get_base_output_dir, get_output_dir, init_output_dirs

    run_id = generate_run_id()
    results_base = str(get_base_output_dir(run_id))
    init_output_dirs(run_id)
    save_pipeline_config(results_base, config)
    save_redteam_data(results_base, rt, red_pairs, windows)

    all_results: list[dict] = []
    experiment_results: dict[str, dict] = {}
    overall_start = time.perf_counter()

    for descriptor in descriptors:
        variant = descriptor.name
        logger.info(f"── Variant: {variant} ──")

        if using_cache:
            # Load from cache
            graph_data = load_graph(cdir, variant)
            feat_data = load_features(cdir, variant)
            top_feats = load_top_features(cdir, variant)

            if graph_data is None or feat_data is None:
                raise FileNotFoundError(
                    f"Cache incomplete for variant '{variant}'. "
                    f"Run 'uv run feature.py --sample {args.sample}' first."
                )

            g = graph_data["graph"]
            build_time = graph_data["build_time"]
            total_events = graph_data["total_events"]
            precomputed = feat_data

            # Use dynamic whitelist from audit, or fallback to descriptor
            whitelist = top_feats if top_feats else list(descriptor.feature_whitelist)
        else:
            # Build from scratch
            data_dir = config.data.lanl_dir
            g, build_time, total_events = build_variant_graph(
                data_dir, windows, config, variant=variant, max_events=args.sample,
            )
            precomputed = None
            whitelist = list(descriptor.feature_whitelist)

        # Score + detect
        mr = _score_detect_graph(
            method_name=variant,
            dataset="LANL-2015",
            g=g,
            red_pairs=red_pairs,
            build_time=build_time,
            total_events=total_events,
            config=config,
            output_dir=str(get_output_dir(run_id, variant)),
            precomputed_features=precomputed,
            feature_whitelist=whitelist,
        )

        # Save results
        save_method_results(
            output_dir=str(get_output_dir(run_id, variant)),
            method=variant,
            g=mr.graph,
            edge_scores=mr.edge_scores,
            paths=mr.paths,
            edge_features=mr.edge_features,
            node_features=mr.node_features,
            graph_features=mr.graph_features,
            anomalous_pairs=mr.metrics["anomalous_pairs"],
            detected_pairs=mr.metrics["detected_pairs"],
        )

        all_results.append(mr.result_dict)
        experiment_results[variant] = {
            "combined_graph": g,
            "combined_edge_scores": mr.edge_scores,
            "combined_threshold": mr.threshold,
            "combined_edge_features": mr.edge_features,
            "red_pairs": frozenset(red_pairs),
            "redteam_times": rt["time"],
        }

    total_duration = time.perf_counter() - overall_start
    logger.info(f"All {len(descriptors)} variants completed in {total_duration:.2f}s")

    # Save results CSVs + JSONs (same format as original)
    results_df = pd.DataFrame(all_results)
    results_dir = Path(results_base)
    results_dir.mkdir(parents=True, exist_ok=True)

    csv_path = results_dir / "metrics.csv"
    results_df.to_csv(csv_path, index=False)
    logger.info(f"Results saved to {csv_path}")

    json_path = results_dir / "experiment_results.json"
    with open(json_path, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    logger.info(f"Results saved to {json_path}")

    details = {}
    for r in all_results:
        method = r["method"]
        dataset = r.get("dataset", "unknown")
        details[f"{dataset}/{method}"] = {k: v for k, v in r.items()}
    details_path = results_dir / "per_method_details.json"
    with open(details_path, "w") as f:
        json.dump(details, f, indent=2, default=str)
    logger.info(f"Per-method details saved to {details_path}")

    # Save pipeline_run.json
    combined_mr = all_results[0] if all_results else {}
    pipeline_run = {
        "run_id": run_id,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": config.to_dict(),
        "data_stats": {
            "data_dir": config.data.lanl_dir,
            "window_seconds": config.data.window_size,
            "using_cache": using_cache,
            "cache_dir": str(cdir),
        },
        "timing": {
            "total_duration": total_duration,
        },
        "final_metrics": {
            dataset: r for r in all_results for dataset in [f"LANL-2015/{r['method']}"]
        },
    }
    with open(results_dir / "pipeline_run.json", "w") as f:
        json.dump(pipeline_run, f, indent=2, default=str)
    logger.info(f"Saved pipeline_run.json to {results_dir}")

    # Generate comparison
    generate_comparison(results_dir=str(results_dir))

    # Generate figures
    from src.visualization import (
        plot_graph_snapshot,
        plot_score_distribution,
        plot_roc_curves,
        plot_detection_timeline,
        plot_method_comparison,
    )

    figures_dir = results_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    combined_result = experiment_results.get("combined")
    if combined_result is not None:
        g = combined_result.get("combined_graph")
        if g is not None:
            plot_graph_snapshot(
                g, str(figures_dir / "graph_snapshot.png"),
                title=f"Combined Auth+Flow Graph ({g.vcount():,} nodes, {g.ecount():,} edges)",
            )
            logger.info("Saved graph_snapshot.png")

        edge_scores = combined_result.get("combined_edge_scores")
        if edge_scores is not None and not edge_scores.empty and g is not None:
            rp = combined_result.get("red_pairs", frozenset())
            threshold = combined_result.get("combined_threshold", 0.0)

            edge_pair_names = compute_edge_pair_names(g)
            labels = pd.Series([
                1.0 if pair in rp else 0.0
                for pair in edge_pair_names
            ], index=edge_scores.index)
            plot_score_distribution(
                edge_scores, labels, str(figures_dir / "score_distribution.png"),
                threshold=threshold, title="Edge Anomaly Score Distribution",
            )
            logger.info("Saved score_distribution.png")

            times = pd.Series(
                [g.es[i]["time"] if "time" in g.es[i].attributes() else 0 for i in range(g.ecount())],
                index=edge_scores.index,
            )
            rt_edge_indices = {i for i, pair in enumerate(edge_pair_names) if pair in rp}
            plot_detection_timeline(
                times, edge_scores, threshold, str(figures_dir / "detection_timeline.png"),
                redteam_edge_indices=rt_edge_indices,
                title="Anomaly Score Timeline with Red Team Events",
            )
            logger.info("Saved detection_timeline.png")

    roc_data = []
    for r in all_results:
        if r.get("auc", 0) > 0:
            roc_data.append({
                "method_name": f"{r['method']} ({r['dataset']})",
                "auc": r["auc"],
            })
    plot_roc_curves(
        roc_data, str(figures_dir / "roc_curves.png"),
        title="ROC Curves — Lateral Movement Detection Methods",
    )
    logger.info("Saved roc_curves.png")

    plot_method_comparison(
        all_results, str(figures_dir / "method_comparison.png"),
        title="Method Performance Comparison",
    )
    logger.info("Saved method_comparison.png")

    _print_summary(results_df)

    log_path = results_dir / "pipeline_log.txt"
    _log_buffer.seek(0)
    log_path.write_text(_log_buffer.read())
    logger.info(f"Pipeline log saved to {log_path}")

    return results_df


def main() -> None:
    run()


if __name__ == "__main__":
    main()
