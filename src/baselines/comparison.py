"""Graph-based result loading and comparison table generation."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from src.baselines.data import (
    _find_redteam_pairs,
    _find_variant_dir,
    compute_pair_metrics,
    optimize_threshold_f1,
)

logger = logging.getLogger(__name__)


def load_graph_based_results(run_dir: Path, variant: str) -> dict | None:
    """Load existing graph-based detection results from the same run_id.

    Tries to find edge_scores.csv and compute metrics from the graph-based pipeline.
    """
    try:
        variant_dir = _find_variant_dir(run_dir, variant)
    except FileNotFoundError:
        return None

    edge_scores_path = variant_dir / "edge_scores.csv"
    graph_edges_path = variant_dir / "graph_edges.csv"

    try:
        redteam_pairs_path = _find_redteam_pairs(run_dir)
    except FileNotFoundError:
        return None

    if not edge_scores_path.exists():
        logger.warning(f"Graph-based edge_scores.csv not found: {edge_scores_path}")
        return None

    try:
        edge_scores_df = pd.read_csv(edge_scores_path)
        graph_edges_df = pd.read_csv(graph_edges_path)

        with open(redteam_pairs_path) as f:
            redteam_pairs = {(str(p["src"]), str(p["dst"])) for p in json.load(f)}

        edge_pairs = list(
            zip(
                graph_edges_df["src"].astype(str).values,
                graph_edges_df["dst"].astype(str).values,
            )
        )

        # Get scores
        if "score" in edge_scores_df.columns:
            scores = edge_scores_df["score"].values
        elif "edge_score" in edge_scores_df.columns:
            scores = edge_scores_df["edge_score"].values
        else:
            # Try first numeric column after src/dst
            numeric_cols = edge_scores_df.select_dtypes(include=[np.number]).columns
            if len(numeric_cols) > 0:
                scores = edge_scores_df[numeric_cols[0]].values
            else:
                logger.warning(f"No score column found in {edge_scores_path}")
                return None

        # Valid mask
        is_self_loop = (
            edge_scores_df["is_self_loop"].values
            if "is_self_loop" in edge_scores_df.columns
            else np.zeros(len(edge_scores_df))
        )
        is_user_edge = (
            edge_scores_df["is_user_edge"].values
            if "is_user_edge" in edge_scores_df.columns
            else np.zeros(len(edge_scores_df))
        )
        valid_mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

        labels = np.fromiter(
            (pair in redteam_pairs for pair in edge_pairs),
            dtype=np.float64,
            count=len(edge_pairs),
        )

        scores_valid = scores[valid_mask]
        labels_valid = labels[valid_mask]
        valid_edge_pairs = [edge_pairs[i] for i in range(len(edge_pairs)) if valid_mask[i]]

        # Optimize threshold
        best_thresh, best_f1 = optimize_threshold_f1(scores_valid, labels_valid.astype(int))

        # Compute pair-level metrics
        graph_metrics = compute_pair_metrics(
            scores_valid, labels_valid, valid_edge_pairs, redteam_pairs, best_thresh
        )

        # AUC
        try:
            if len(np.unique(labels_valid)) > 1:
                graph_auc = float(roc_auc_score(labels_valid, scores_valid))
            else:
                graph_auc = 0.0
        except ValueError:
            graph_auc = 0.0

        return {
            "method": "Graph-based (weighted sum + path boost)",
            "threshold": best_thresh,
            "f1_at_threshold": best_f1,
            "auc_edge": graph_auc,
            "pair_metrics": graph_metrics,
        }

    except Exception as e:
        logger.warning(f"Failed to load graph-based results for {variant}: {e}")
        return None


def build_comparison_table(
    per_variant_results: dict[str, dict],
    graph_results: dict[str, dict | None],
) -> str:
    """Build a markdown comparison table."""
    lines = [
        "# Baseline Comparison: Graph-based vs One-Class SVM vs Isolation Forest",
        "",
        "## Per-Variant Results",
        "",
    ]

    for variant in ["combined", "auth_only", "flow_only"]:
        if variant not in per_variant_results:
            continue

        lines.append(f"### {variant}")
        lines.append("")
        lines.append(
            "| Method | Recall | FPR | F1 | Precision | AUC |"
        )
        lines.append(
            "|--------|--------|-----|----|-----------|-----|"
        )

        # Graph-based
        graph = graph_results.get(variant)
        if graph:
            pm = graph.get("pair_metrics", {})
            lines.append(
                f"| Graph-based | {pm.get('recall', 'N/A'):.4f} | "
                f"{pm.get('fpr', 'N/A'):.4f} | {pm.get('f1', 'N/A'):.4f} | "
                f"{pm.get('precision', 'N/A'):.4f} | {graph.get('auc_edge', 'N/A'):.4f} |"
            )
        else:
            lines.append("| Graph-based | N/A | N/A | N/A | N/A | N/A |")

        # Baselines
        variant_results = per_variant_results[variant]
        for method_key, method_name in [
            ("one_class_svm", "One-Class SVM"),
            ("isolation_forest", "Isolation Forest"),
        ]:
            if method_key in variant_results:
                pm = variant_results[method_key].get("pair_metrics", {})
                lines.append(
                    f"| {method_name} | {pm.get('recall', 'N/A'):.4f} | "
                    f"{pm.get('fpr', 'N/A'):.4f} | {pm.get('f1', 'N/A'):.4f} | "
                    f"{pm.get('precision', 'N/A'):.4f} | "
                    f"{variant_results[method_key].get('auc_edge', 'N/A'):.4f} |"
                )
            else:
                lines.append(f"| {method_name} | N/A | N/A | N/A | N/A | N/A |")

        lines.append("")

    return "\n".join(lines)
