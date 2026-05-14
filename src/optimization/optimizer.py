from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.optimize import minimize
from sklearn.metrics import roc_auc_score

logger = logging.getLogger(__name__)

RANK_TRANSFORM_FEATURES = frozenset({"edge_rarity", "protocol_rarity"})


class WeightOptimizer:
    def __init__(self, features_df: pd.DataFrame, labels: np.ndarray, feature_names: list[str]):
        self.features_df = features_df
        self.labels = labels
        self.feature_names = feature_names
        self._log: list[dict] = []
        self._best_auc = -np.inf
        self._best_weights: np.ndarray | None = None
        self._iteration = 0
        self._start_time: float = 0.0

    def _score_with_weights(self, w_array: np.ndarray) -> np.ndarray:
        score = np.zeros(len(self.features_df))
        for i, feat_name in enumerate(self.feature_names):
            feat_values = self.features_df[feat_name].values.copy()
            if feat_name in RANK_TRANSFORM_FEATURES:
                feat_values = pd.Series(feat_values).rank(pct=True).values
            score += w_array[i] * feat_values
        return score

    def _objective(self, w_array: np.ndarray) -> float:
        if len(np.unique(self.labels)) < 2:
            return 0.0
        scores = self._score_with_weights(w_array)
        auc = roc_auc_score(self.labels, scores)
        return -auc

    def _callback(self, xk: np.ndarray) -> None:
        self._iteration += 1
        now = time.time()
        elapsed = now - self._start_time

        if len(np.unique(self.labels)) < 2:
            return

        scores = self._score_with_weights(xk)
        auc = roc_auc_score(self.labels, scores)
        neg_auc = -auc
        delta = auc - self._best_auc if self._best_auc > -np.inf else 0.0

        weights_dict = {name: float(xk[i]) for i, name in enumerate(self.feature_names)}

        entry = {
            "iteration": self._iteration,
            "weights": weights_dict,
            "auc": float(auc),
            "neg_auc": float(neg_auc),
            "improvement_delta": float(delta),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": float(elapsed),
        }
        self._log.append(entry)

        if auc > self._best_auc:
            self._best_auc = auc
            self._best_weights = xk.copy()
            logger.info(
                f"  Iter {self._iteration:4d} | AUC={auc:.6f} | Δ={delta:+.6f} | NEW BEST | "
                f"w={np.array2string(xk, precision=4, separator=', ')}"
            )
        else:
            logger.debug(
                f"  Iter {self._iteration:4d} | AUC={auc:.6f} | Δ={delta:+.6f} | "
                f"best={self._best_auc:.6f}"
            )

    def optimize(self, method: str = "nelder-mead", output_dir: str | None = None, **kwargs) -> dict:
        self._start_time = time.time()
        self._log = []
        self._iteration = 0
        self._best_auc = -np.inf
        self._best_weights = None

        n = len(self.feature_names)
        x0 = np.full(n, 1.0 / n)

        logger.info("=" * 70)
        logger.info("Starting weight optimization")
        logger.info(f"  Method: {method}")
        logger.info(f"  Features ({n}): {self.feature_names}")
        logger.info(f"  Initial weights: {np.array2string(x0, precision=4)}")
        logger.info(f"  Samples: {len(self.labels)}, positives: {int(self.labels.sum())}, "
                     f"negatives: {int((self.labels == 0).sum())}")
        logger.info("=" * 70)

        initial_auc = -self._objective(x0)
        logger.info(f"  Initial AUC (equal weights): {initial_auc:.6f}")

        options = {"maxiter": 500, "xatol": 1e-6, "fatol": 1e-8, "adaptive": True}
        options.update(kwargs.get("options", {}))

        result = minimize(
            self._objective,
            x0,
            method=method,
            callback=self._callback,
            options=options,
        )

        total_time = time.time() - self._start_time

        optimal_w = result.x if self._best_weights is None else self._best_weights
        best_auc = -result.fun if self._best_auc == -np.inf else self._best_auc

        weights_dict = {name: float(optimal_w[i]) for i, name in enumerate(self.feature_names)}
        initial_weights_dict = {name: float(x0[i]) for i, name in enumerate(self.feature_names)}

        convergence_reason = "converged" if result.success else result.message
        if isinstance(convergence_reason, bytes):
            convergence_reason = convergence_reason.decode("utf-8", errors="replace")

        output = {
            **weights_dict,
            "auc": float(best_auc),
            "iterations": self._iteration,
            "converged": bool(result.success),
            "total_time_seconds": float(total_time),
            "convergence_reason": convergence_reason,
        }

        logger.info("=" * 70)
        logger.info("Optimization complete")
        logger.info(f"  Converged: {result.success} ({convergence_reason})")
        logger.info(f"  Iterations: {self._iteration}")
        logger.info(f"  Total time: {total_time:.2f}s")
        logger.info(f"  Initial AUC: {initial_auc:.6f}")
        logger.info(f"  Optimized AUC: {best_auc:.6f}")
        logger.info(f"  Improvement: {best_auc - initial_auc:+.6f} "
                     f"({(best_auc - initial_auc) / max(initial_auc, 1e-9) * 100:+.2f}%)")
        logger.info("  Final weights:")
        for name, w in weights_dict.items():
            logger.info(f"    {name}: {w:.6f}")
        logger.info("=" * 70)

        if output_dir:
            self._save_outputs(output_dir, output, initial_auc, initial_weights_dict, x0, optimal_w, result, total_time, convergence_reason)

        return output

    def _save_outputs(
        self,
        output_dir: str,
        output: dict,
        initial_auc: float,
        initial_weights: dict,
        x0: np.ndarray,
        optimal_w: np.ndarray,
        result,
        total_time: float,
        convergence_reason: str,
    ) -> None:
        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)
        ts = datetime.now(timezone.utc).isoformat()

        # optimization_log.json
        log_path = out / "optimization_log.json"
        with open(log_path, "w") as f:
            json.dump({"timestamp": ts, "trace": self._log}, f, indent=2)
        logger.info(f"Saved optimization log to {log_path}")

        # optimized_weights.json
        weights_path = out / "optimized_weights.json"
        weights_payload = {
            "timestamp": ts,
            "weights": {name: float(optimal_w[i]) for i, name in enumerate(self.feature_names)},
            "auc": output["auc"],
            "method": "nelder-mead",
            "iterations": self._iteration,
            "converged": output["converged"],
            "initial_weights": initial_weights,
            "convergence_reason": convergence_reason,
            "total_time_seconds": total_time,
            "feature_names": self.feature_names,
        }
        with open(weights_path, "w") as f:
            json.dump(weights_payload, f, indent=2)
        logger.info(f"Saved optimized weights to {weights_path}")

        # feature_contribution.csv
        scores = self._score_with_weights(optimal_w)
        contrib_df = self.features_df[self.feature_names].copy()
        for i, name in enumerate(self.feature_names):
            feat_vals = self.features_df[name].values.copy()
            if name in RANK_TRANSFORM_FEATURES:
                feat_vals = pd.Series(feat_vals).rank(pct=True).values
            contrib_df[f"{name}_weighted"] = optimal_w[i] * feat_vals
        contrib_df["total_score"] = scores
        contrib_df["label"] = self.labels
        contrib_path = out / "feature_contribution.csv"
        contrib_df.to_csv(contrib_path, index=False)
        logger.info(f"Saved feature contribution to {contrib_path}")

        # optimization_comparison.json
        comparison = {
            "timestamp": ts,
            "equal_weight_auc": float(initial_auc),
            "optimized_auc": output["auc"],
            "improvement_pct": float(
                (output["auc"] - initial_auc) / max(initial_auc, 1e-9) * 100
            ),
            "per_feature": {},
        }
        for i, name in enumerate(self.feature_names):
            comparison["per_feature"][name] = {
                "weight_before": float(x0[i]),
                "weight_after": float(optimal_w[i]),
                "delta": float(optimal_w[i] - x0[i]),
            }
        comp_path = out / "optimization_comparison.json"
        with open(comp_path, "w") as f:
            json.dump(comparison, f, indent=2)
        logger.info(f"Saved optimization comparison to {comp_path}")


def load_run_data(run_dir: str) -> tuple[pd.DataFrame, np.ndarray]:
    run_path = Path(run_dir)

    edge_features_path = run_path / "combined" / "edge_features.csv"
    node_features_path = run_path / "combined" / "node_features.csv"
    graph_edges_path = run_path / "combined" / "graph_edges.csv"
    redteam_path = run_path / "redteam" / "redteam_pairs.json"

    logger.info(f"Loading run data from {run_dir}")

    edge_features = pd.read_csv(edge_features_path)
    logger.info(f"  edge_features.csv: {edge_features.shape[0]:,} rows, {edge_features.shape[1]} columns")
    logger.info(f"  Columns: {list(edge_features.columns)}")

    node_features = pd.read_csv(node_features_path)
    logger.info(f"  node_features.csv: {node_features.shape[0]:,} rows, {node_features.shape[1]} columns")

    graph_edges = pd.read_csv(graph_edges_path)
    logger.info(f"  graph_edges.csv: {graph_edges.shape[0]:,} rows, {graph_edges.shape[1]} columns")

    with open(redteam_path) as f:
        redteam_pairs = json.load(f)
    redteam_set = {(p["src"], p["dst"]) for p in redteam_pairs}
    logger.info(f"  redteam_pairs.json: {len(redteam_pairs)} pairs, {len(redteam_set)} unique")

    # Join dst_fan_out_ratio from node_features
    fan_out_map = node_features.set_index("node")["fan_out_ratio"]
    dst_nodes = graph_edges["dst"].values
    edge_features["dst_fan_out_ratio"] = pd.Series(dst_nodes).map(fan_out_map).values
    nan_count = edge_features["dst_fan_out_ratio"].isna().sum()
    logger.info(f"  Joined dst_fan_out_ratio: {nan_count} NaN values")

    # Create binary labels
    src_dst = list(zip(graph_edges["src"].values, graph_edges["dst"].values))
    labels = np.array([1 if pair in redteam_set else 0 for pair in src_dst], dtype=np.int32)
    logger.info(f"  Labels: {int(labels.sum())} positive, {int((labels == 0).sum())} negative "
                f"({labels.sum() / len(labels) * 100:.2f}% positive)")

    # Filter valid edges
    valid_mask = (edge_features["is_self_loop"].values == 0) & (edge_features["is_user_edge"].values == 0)
    valid_count = valid_mask.sum()
    total_count = len(edge_features)
    logger.info(f"  Valid edges: {valid_count:,} / {total_count:,} "
                f"({valid_count / total_count * 100:.1f}%)")

    filtered_features = edge_features.loc[valid_mask].reset_index(drop=True)
    filtered_labels = labels[valid_mask]
    filtered_edges = graph_edges.loc[valid_mask].reset_index(drop=True)

    logger.info(f"  After filtering: {len(filtered_features):,} rows, {filtered_features.shape[1]} columns")
    logger.info(f"  Filtered labels: {int(filtered_labels.sum())} positive, "
                f"{int((filtered_labels == 0).sum())} negative")

    nan_counts = filtered_features.isna().sum()
    features_with_nan = nan_counts[nan_counts > 0]
    if len(features_with_nan) > 0:
        logger.warning(f"  NaN counts per column: {features_with_nan.to_dict()}")
    else:
        logger.info("  No NaN values in features")

    # Store filtered edges index for reference
    filtered_features.attrs["graph_edges"] = filtered_edges

    return filtered_features, filtered_labels
