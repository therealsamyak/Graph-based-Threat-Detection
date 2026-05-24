"""Per-variant evaluation orchestration and summary building."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TypeAlias

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from src.baselines.data import find_variant_dir, load_variant_data, load_feature_whitelist, prepare_features_and_labels
from src.baselines.models import BaselineResult, run_isolation_forest_baseline, run_one_class_svm

logger = logging.getLogger(__name__)

VariantResults: TypeAlias = dict[str, BaselineResult]
GraphResults: TypeAlias = dict[str, dict[str, object] | None]


def split_unsupervised_train_eval(labels: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Train one-class models on normal edges; evaluate on held-out normals plus positives."""
    normal_idx = np.flatnonzero(labels == 0)
    positive_idx = np.flatnonzero(labels == 1)

    if len(normal_idx) < 2:
        raise ValueError(
            f"Need at least two normal edges for one-class train/eval split; got {len(normal_idx)}"
        )

    normal_train_idx, normal_eval_idx = train_test_split(
        normal_idx,
        test_size=0.5,
        random_state=42,
    )
    eval_idx = np.concatenate([normal_eval_idx, positive_idx])
    if len(eval_idx) == 0:
        raise ValueError("Evaluation split is empty")

    return np.asarray(normal_train_idx, dtype=int), np.asarray(eval_idx, dtype=int)


def _pop_scores(result: BaselineResult) -> np.ndarray:
    scores = result.pop("eval_scores")
    if not isinstance(scores, np.ndarray):
        raise TypeError(f"Expected numpy eval_scores, got {type(scores).__name__}")
    return scores


def evaluate_variant(
    run_dir: Path,
    variant: str,
    output_dir: Path,
) -> VariantResults:
    """Run all baselines on a single variant and save results."""
    logger.info(f"{'=' * 60}")
    logger.info(f"Evaluating variant: {variant}")
    logger.info(f"{'=' * 60}")

    variant_output_dir = output_dir / variant
    variant_output_dir.mkdir(parents=True, exist_ok=True)

    edge_features_df, _graph_edges_df, edge_pairs, redteam_pairs = load_variant_data(
        run_dir, variant
    )
    variant_dir = find_variant_dir(run_dir, variant)
    whitelist = load_feature_whitelist(variant_dir, variant)
    X_valid, labels_valid, valid_edge_pairs = prepare_features_and_labels(
        edge_features_df, edge_pairs, redteam_pairs, variant, feature_whitelist=whitelist,
    )

    train_idx, eval_idx = split_unsupervised_train_eval(labels_valid)

    X_train = X_valid.iloc[train_idx].reset_index(drop=True)
    X_eval = X_valid.iloc[eval_idx].reset_index(drop=True)
    y_eval = labels_valid[eval_idx]
    eval_edge_pairs = [valid_edge_pairs[i] for i in eval_idx]

    logger.info(
        f"Split: {len(X_train)} normal train edges, "
        f"{len(X_eval)} eval edges ({int(y_eval.sum())} positive)"
    )

    all_results: VariantResults = {}

    oc_svm_result = run_one_class_svm(X_train, X_eval, eval_edge_pairs, redteam_pairs)
    oc_svm_scores = _pop_scores(oc_svm_result)
    all_results["one_class_svm"] = oc_svm_result

    with open(variant_output_dir / "one_class_svm_results.json", "w") as f:
        json.dump(oc_svm_result, f, indent=2, default=str)
    logger.info(f"Saved {variant_output_dir / 'one_class_svm_results.json'}")

    iforest_result = run_isolation_forest_baseline(
        X_train, X_eval, eval_edge_pairs, redteam_pairs
    )
    iforest_scores = _pop_scores(iforest_result)
    all_results["isolation_forest"] = iforest_result

    with open(variant_output_dir / "iforest_results.json", "w") as f:
        json.dump(iforest_result, f, indent=2, default=str)
    logger.info(f"Saved {variant_output_dir / 'iforest_results.json'}")

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


def _summary_metrics(result: dict[str, object]) -> dict[str, object]:
    pair_metrics = result.get("pair_metrics")
    if not isinstance(pair_metrics, dict):
        raise TypeError("Missing pair_metrics in baseline result")

    return {
        "recall": pair_metrics.get("recall"),
        "fpr": pair_metrics.get("fpr"),
        "f1": pair_metrics.get("f1"),
        "precision": pair_metrics.get("precision"),
        "auc": result.get("auc_edge"),
        "num_detected_pairs": pair_metrics.get("num_detected_pairs"),
        "num_redteam_pairs": pair_metrics.get("num_redteam_pairs"),
    }


def build_summary(
    variants_to_eval: list[str],
    per_variant_results: dict[str, VariantResults],
    graph_results: GraphResults,
    run_id: str,
    timestamp: str,
    output_dir: Path,
) -> dict[str, object]:
    """Build and save the JSON summary with per-variant metrics."""
    summary: dict[str, object] = {
        "timestamp": timestamp,
        "run_id": run_id,
        "variants_evaluated": variants_to_eval,
        "methods": ["One-Class SVM", "Isolation Forest"],
        "per_variant_summary": {},
    }

    per_variant_summary: dict[str, dict[str, object]] = {}
    for variant in variants_to_eval:
        variant_summary: dict[str, object] = {}
        for method_key in ["one_class_svm", "isolation_forest"]:
            result = per_variant_results.get(variant, {}).get(method_key)
            if result is not None:
                variant_summary[method_key] = _summary_metrics(result)

        graph_result = graph_results.get(variant)
        if graph_result is not None:
            variant_summary["graph_based"] = _summary_metrics(graph_result)

        per_variant_summary[variant] = variant_summary

    summary["per_variant_summary"] = per_variant_summary

    with open(output_dir / "summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'summary.json'}")

    with open(output_dir / "per_variant_results.json", "w") as f:
        json.dump(per_variant_results, f, indent=2, default=str)
    logger.info(f"Saved {output_dir / 'per_variant_results.json'}")

    return summary
