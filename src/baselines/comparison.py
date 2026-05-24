"""Graph-based result loading and comparison table generation."""

from __future__ import annotations

import logging
from numbers import Real
from pathlib import Path

import pandas as pd

from src.baselines.data import evaluate_scores, find_variant_dir, load_variant_data, valid_edge_mask

logger = logging.getLogger(__name__)

GraphResult = dict[str, object]
VariantResults = dict[str, GraphResult]


def load_graph_based_results(run_dir: Path, variant: str) -> GraphResult | None:
    """Load existing graph-based detection scores from the same run_id."""
    try:
        variant_dir = find_variant_dir(run_dir, variant)
        edge_features_df, _graph_edges_df, edge_pairs, redteam_pairs = load_variant_data(
            run_dir, variant
        )
    except FileNotFoundError as exc:
        logger.warning(f"Graph-based results unavailable for {variant}: {exc}")
        return None

    edge_scores_path = variant_dir / "edge_scores.csv"
    if not edge_scores_path.exists():
        logger.warning(f"Graph-based edge_scores.csv not found: {edge_scores_path}")
        return None

    edge_scores_df = pd.read_csv(edge_scores_path)
    if "score" not in edge_scores_df.columns:
        raise ValueError(f"Expected 'score' column in {edge_scores_path}")
    if len(edge_scores_df) != len(edge_pairs):
        raise ValueError(
            f"Score row count ({len(edge_scores_df)}) does not match graph edge count ({len(edge_pairs)})"
        )

    mask = valid_edge_mask(edge_features_df)
    scores = edge_scores_df["score"].to_numpy(dtype=float)[mask]
    valid_edge_pairs = [edge_pairs[i] for i in range(len(edge_pairs)) if mask[i]]

    threshold, best_f1, graph_metrics = evaluate_scores(
        scores,
        valid_edge_pairs,
        redteam_pairs,
    )

    return {
        "method": "Graph-based (weighted sum + path boost)",
        "threshold": threshold,
        "f1_at_threshold": best_f1,
        "auc_edge": float(graph_metrics["auc"]),
        "pair_metrics": graph_metrics,
    }


def _format_metric(value: object) -> str:
    if isinstance(value, Real):
        return f"{float(value):.4f}"
    return "N/A"


def _table_row(method_name: str, result: GraphResult | None) -> str:
    if result is None:
        return f"| {method_name} | N/A | N/A | N/A | N/A | N/A |"

    pair_metrics = result.get("pair_metrics")
    if not isinstance(pair_metrics, dict):
        return f"| {method_name} | N/A | N/A | N/A | N/A | N/A |"

    return (
        f"| {method_name} | {_format_metric(pair_metrics.get('recall'))} | "
        f"{_format_metric(pair_metrics.get('fpr'))} | {_format_metric(pair_metrics.get('f1'))} | "
        f"{_format_metric(pair_metrics.get('precision'))} | "
        f"{_format_metric(result.get('auc_edge'))} |"
    )


def build_comparison_table(
    per_variant_results: dict[str, VariantResults],
    graph_results: dict[str, GraphResult | None],
) -> str:
    """Build a markdown comparison table."""
    lines = [
        "# Baseline Comparison: Graph-based vs One-Class SVM vs Isolation Forest",
        "",
        "## Per-Variant Results",
        "",
    ]

    for variant in sorted(per_variant_results):
        lines.append(f"### {variant}")
        lines.append("")
        lines.append("| Method | Recall | FPR | F1 | Precision | AUC |")
        lines.append("|--------|--------|-----|----|-----------|-----|")
        lines.append(_table_row("Graph-based", graph_results.get(variant)))

        variant_results = per_variant_results[variant]
        for method_key, method_name in [
            ("one_class_svm", "One-Class SVM"),
            ("isolation_forest", "Isolation Forest"),
        ]:
            lines.append(_table_row(method_name, variant_results.get(method_key)))

        lines.append("")

    return "\n".join(lines)
