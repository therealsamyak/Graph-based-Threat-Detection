"""I/O helpers: persist method results, redteam data, and pipeline config."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import igraph as ig
import pandas as pd

logger = logging.getLogger(__name__)


def save_method_results(
    output_dir: str,
    method: str,
    g: ig.Graph,
    edge_scores: pd.Series,
    paths: pd.DataFrame,
    edge_features: pd.DataFrame,
    node_features: pd.DataFrame,
    graph_features: dict,
    anomalous_pairs: set[tuple[str, str]],
    detected_pairs: set[tuple[str, str]],
) -> None:
    """Save per-method CSVs and JSONs under *output_dir*.

    File layout matches the original pipeline conventions:
        edge_scores.csv, paths.csv, anomalous_paths.csv,
        node_features.csv, edge_features.csv, graph_features.json,
        graph_edges.csv, graph_nodes.csv, detected_redteam_pairs.json
    """
    method_dir = Path(output_dir)
    method_dir.mkdir(parents=True, exist_ok=True)

    edge_scores.to_csv(method_dir / "edge_scores.csv", header=["score"])
    logger.info(f"  Saved edge_scores.csv ({len(edge_scores):,} edges)")

    if len(paths) > 0:
        paths_save = paths.copy()
        paths_save["path_nodes"] = paths_save["path_nodes"].apply(
            lambda x: " -> ".join(x) if isinstance(x, list) else str(x)
        )
        paths_save["path_edges"] = paths_save["path_edges"].apply(
            lambda x: ",".join(str(i) for i in x) if isinstance(x, list) else str(x)
        )
        paths_save.to_csv(method_dir / "paths.csv", index=False)
        logger.info(f"  Saved paths.csv ({len(paths_save):,} paths)")

    if len(anomalous_pairs) > 0:
        ap_rows = [{"src": s, "dst": d} for s, d in anomalous_pairs]
        pd.DataFrame(ap_rows).to_csv(method_dir / "anomalous_paths.csv", index=False)
        logger.info(f"  Saved anomalous_paths.csv ({len(ap_rows):,} anomalous edges)")

    node_features.to_csv(method_dir / "node_features.csv")
    edge_features.to_csv(method_dir / "edge_features.csv")
    with open(method_dir / "graph_features.json", "w") as f:
        json.dump(graph_features, f, indent=2)
    logger.info("  Saved node_features.csv, edge_features.csv, graph_features.json")

    # graph_edges.csv
    edge_rows = []
    for e in g.es:
        attrs = e.attributes()
        edge_rows.append({
            "src": g.vs[e.source]["name"],
            "dst": g.vs[e.target]["name"],
            **{k: v for k, v in attrs.items()},
        })
    pd.DataFrame(edge_rows).to_csv(method_dir / "graph_edges.csv", index=False)

    # graph_nodes.csv
    node_rows = [
        {
            "name": v["name"],
            **{k: v for k, v in v.attributes().items() if k != "name"},
        }
        for v in g.vs
    ]
    pd.DataFrame(node_rows).to_csv(method_dir / "graph_nodes.csv", index=False)
    logger.info(
        f"  Saved graph_edges.csv ({g.ecount():,}), graph_nodes.csv ({g.vcount():,})"
    )

    if detected_pairs:
        with open(method_dir / "detected_redteam_pairs.json", "w") as f:
            json.dump(
                [{"src": s, "dst": d} for s, d in sorted(detected_pairs)], f, indent=2
            )
        logger.info(
            f"  Saved detected_redteam_pairs.json ({len(detected_pairs)} pairs)"
        )


def save_redteam_data(
    results_dir: str,
    rt: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    windows: list[tuple[int, int]],
) -> None:
    """Save redteam events, window intervals, and red pairs JSONs."""
    redteam_dir = Path(results_dir) / "redteam"
    redteam_dir.mkdir(parents=True, exist_ok=True)

    rt.to_csv(redteam_dir / "redteam_events.csv", index=False)
    with open(redteam_dir / "window_intervals.json", "w") as f:
        json.dump([{"start": s, "end": e} for s, e in windows], f, indent=2)
    with open(redteam_dir / "redteam_pairs.json", "w") as f:
        json.dump([{"src": s, "dst": d} for s, d in sorted(red_pairs)], f, indent=2)
    logger.info(f"  Saved redteam data to {redteam_dir}")


def save_pipeline_config(results_dir: str, config) -> None:
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)
    data = config.to_dict() if hasattr(config, "to_dict") else config
    with open(results_path / "pipeline_config.json", "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"  Saved pipeline_config.json to {results_path}")


def save_experiment_summary(
    results_dir: str,
    all_results: list[dict],
) -> None:
    """Write metrics.csv and results JSON to *results_dir*."""
    results_path = Path(results_dir)
    results_path.mkdir(parents=True, exist_ok=True)

    df = pd.DataFrame(all_results)
    df.to_csv(results_path / "metrics.csv", index=False)
    with open(results_path / "experiment_results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    logger.info(f"  Saved metrics.csv ({len(all_results)} rows) to {results_path}")
