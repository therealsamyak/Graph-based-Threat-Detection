"""Per-variant evaluation orchestration and summary building."""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.baselines.comparison import load_graph_based_results
from src.baselines.data import (
    _find_variant_dir,
    load_variant_data,
    prepare_features_and_labels,
)
from src.baselines.models import run_isolation_forest_baseline, run_one_class_svm

logger = logging.getLogger(__name__)


def evaluate_variant(
    run_dir: Path,
    variant: str,
    output_dir: Path,
) -> dict:
    """Run all baselines on a single variant and save results.

    Returns dict with per-method results.
    """
    logger.info(f"{'=' * 60}")
    logger.info(f"Evaluating variant: {variant}")
    logger.info(f"{'=' * 60}")

    variant_output_dir = output_dir / variant
    variant_output_dir.mkdir(parents=True, exist_ok=True)

    # ── Load data ──
    edge_features_df, graph_edges_df, edge_pairs, redteam_pairs = load_variant_data(
        run_dir, variant
    )

    # ── Prepare features and labels ──
    X_valid, labels_valid, valid_mask, valid_edge_pairs = prepare_features_and_labels(
        edge_features_df, graph_edges_df, edge_pairs, redteam_pairs, variant
    )

    # ── Stratified split (50/50, seed=42) ──
    train_idx, eval_idx = train_test_split(
        np.arange(len(X_valid)),
        test_size=0.5,
        stratify=labels_valid,
        random_state=42,
    )

    X_train = X_valid.iloc[train_idx].reset_index(drop=True)
    y_train = labels_valid[train_idx]
    X_eval = X_valid.iloc[eval_idx].reset_index(drop=True)
    y_eval = labels_valid[eval_idx]
    eval_edge_pairs = [valid_edge_pairs[i] for i in eval_idx]

    logger.info(
        f"Split: {len(X_train)} train edges ({int(y_train.sum())} positive), "
        f"{len(X_eval)} eval edges ({int(y_eval.sum())} positive)"
    )

    # ── Run baselines ──
    all_results = {}

    oc_svm_result = run_one_class_svm(
        X_train, y_train, X_eval, y_eval, eval_edge_pairs, redteam_pairs
    )
    oc_svm_scores = oc_svm_result.pop("eval_scores")
    all_results["one_class_svm"] = oc_svm_result

    with open(variant_output_dir / "one_class_svm_results.json", "w") as f:
        json.dump(oc_svm_result, f, indent=2, default=str)
    logger.info(f"Saved {variant_output_dir / 'one_class_svm_results.json'}")

    # Isolation Forest baseline
    iforest_result = run_isolation_forest_baseline(
        X_train, y_train, X_eval, y_eval, eval_edge_pairs, redteam_pairs
    )
    iforest_scores = iforest_result.pop("eval_scores")
    all_results["isolation_forest"] = iforest_result

    with open(variant_output_dir / "iforest_results.json", "w") as f:
        json.dump(iforest_result, f, indent=2, default=str)
    logger.info(f"Saved {variant_output_dir / 'iforest_results.json'}")

    # Save edge scores
    scores_df = pd.DataFrame(
        {
            "src": [p[0] for p in eval_edge_pairs],
            "dst": [p[1] for p in eval_edge_pairs],
            "label": y_eval.astype(int),
            "one_class_svm_score": oc_svm_scores,
            "isolation_forest_score": iforest_scores,
        }
    )
    scores_df.to_csv(variant_output_dir / "edge_scores.csv", index=False)
    logger.info(f"Saved {variant_output_dir / 'edge_scores.csv'}")

    return all_results


def build_summary(
    variants_to_eval: list[str],
    per_variant_results: dict[str, dict],
    graph_results: dict[str, dict | None],
    run_id: str,
    timestamp: str,
    output_dir: Path,
) -> dict:
    """Build and save the JSON summary with per-variant metrics."""
    summary: dict = {
        "timestamp": timestamp,
        "run_id": run_id,
        "variants_evaluated": variants_to_eval,
        "methods": ["One-Class SVM", "Isolation Forest"],
        "per_variant_summary": {},
    }

    for variant in variants_to_eval:
        variant_summary: dict = {}
        for method_key in ["one_class_svm", "isolation_forest"]:
            if method_key in per_variant_results.get(variant, {}):
                m = per_variant_results[variant][method_key]
                pm = m.get("pair_metrics", {})
                variant_summary[method_key] = {
                    "recall": pm.get("recall"),
                    "fpr": pm.get("fpr"),
                    "f1": pm.get("f1"),
                    "precision": pm.get("precision"),
                    "auc": m.get("auc_edge"),
                    "num_detected_pairs": pm.get("num_detected_pairs"),
                    "num_redteam_pairs": pm.get("num_redteam_pairs"),
                }

        # Add graph-based if available
        if graph_results.get(variant):
            g = graph_results[variant]
            pm = g.get("pair_metrics", {})
            variant_summary["graph_based"] = {
                "recall": pm.get("recall"),
                "fpr": pm.get("fpr"),
                "f1": pm.get("f1"),
                "precision": pm.get("precision"),
                "auc": g.get("auc_edge"),
                "num_detected_pairs": pm.get("num_detected_pairs"),
                "num_redteam_pairs": pm.get("num_redteam_pairs"),
            }

        summary["per_variant_summary"][variant] = variant_summary

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'summary.json'}")

    # Save per-variant detailed results
    with open(output_dir / "per_variant_results.json", "w") as f:
        json.dump(per_variant_results, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'per_variant_results.json'}")

    return summary
