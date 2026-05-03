"""LANL-2015 unsupervised baselines: IF, LOF, OCSVM, EE, PCA on 12-dim edge features."""

import logging
import warnings

import numpy as np
import pandas as pd
from sklearn.covariance import EllipticEnvelope
from sklearn.decomposition import PCA
from sklearn.ensemble import IsolationForest
from sklearn.metrics import roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler
from sklearn.svm import OneClassSVM

logger = logging.getLogger(__name__)

# Percentiles for threshold sweeping (matches LaTeX Section 4.6)
THRESHOLD_PERCENTILES = [90, 95, 97, 99, 99.5, 99.9]


def _prepare_features(edge_features: pd.DataFrame) -> tuple[np.ndarray, pd.Index]:
    """Select 12 core features and return as numpy array."""
    # Use the 12 features described in LaTeX Section 4.2
    feature_cols = [
        "edge_rarity", "src_out_degree", "dst_in_degree", "src_fan_out",
        "normalized_weight", "is_self_loop", "is_user_edge",
        "is_ntlm", "is_network_logon", "auth_success",
        "is_unusual_dst_port", "is_ephemeral",
        "protocol_rarity", "byte_per_packet_ratio", "duration_z_score",
    ]
    # Use only columns that exist in the dataframe
    available_cols = [c for c in feature_cols if c in edge_features.columns]
    if not available_cols:
        # Fallback to all numeric columns
        available_cols = edge_features.select_dtypes(include=[np.number]).columns.tolist()

    features = edge_features[available_cols].values.astype(np.float64)
    features = np.nan_to_num(features, nan=0.0, posinf=0.0, neginf=0.0)
    return features, edge_features.index


def _evaluate(
    edge_features: pd.DataFrame,
    anomaly_scores: np.ndarray,
    red_pairs: set[tuple[str, str]],
    graph,
    method_name: str,
) -> dict:
    """Evaluate baseline against red-team pairs in edge space and pair space."""
    n_edges = len(anomaly_scores)
    if n_edges == 0:
        return {"method_name": method_name, "auc": 0.0, "recall": 0.0, "fpr": 0.0, "f1": 0.0}

    # Build labels: 1 if edge's (src, dst) is a red-team pair
    labels = np.zeros(n_edges, dtype=float)
    for i in range(n_edges):
        e = graph.es[i]
        pair = (graph.vs[e.source]["name"], graph.vs[e.target]["name"])
        if pair in red_pairs:
            labels[i] = 1.0

    # AUC
    try:
        auc = roc_auc_score(labels, anomaly_scores)
    except Exception:
        auc = 0.0

    # Threshold sweeping to maximize F1 in pair-space
    best_f1 = 0.0
    best_recall = 0.0
    best_fpr = 0.0
    best_threshold = 0.0

    for pct in THRESHOLD_PERCENTILES:
        thr = float(np.percentile(anomaly_scores, pct))
        flagged = anomaly_scores > thr

        # Pair-space metrics
        flagged_pairs: set[tuple[str, str]] = set()
        for i in range(n_edges):
            if flagged[i]:
                e = graph.es[i]
                flagged_pairs.add((graph.vs[e.source]["name"], graph.vs[e.target]["name"]))

        all_pairs: set[tuple[str, str]] = set()
        for i in range(n_edges):
            e = graph.es[i]
            all_pairs.add((graph.vs[e.source]["name"], graph.vs[e.target]["name"]))

        detected_rt = flagged_pairs & red_pairs
        recall = len(detected_rt) / max(len(red_pairs), 1)
        fp = len(flagged_pairs - red_pairs)
        tn = len(all_pairs - flagged_pairs - red_pairs)
        fpr = fp / max(fp + tn, 1)
        precision = len(detected_rt) / max(len(flagged_pairs), 1)
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

        if f1 > best_f1:
            best_f1 = f1
            best_recall = recall
            best_fpr = fpr
            best_threshold = thr

    return {
        "method_name": method_name,
        "auc": round(auc, 4),
        "recall": round(best_recall, 4),
        "fpr": round(best_fpr, 4),
        "f1": round(best_f1, 4),
        "threshold": round(best_threshold, 4),
    }


def run_isolation_forest(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> dict:
    """Isolation Forest: 100 trees, 5% contamination."""
    X, idx = _prepare_features(edge_features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = IsolationForest(n_estimators=100, contamination=0.05, random_state=42)
    model.fit(X_scaled)
    # score_samples: lower = more anomalous
    scores = -model.score_samples(X_scaled)
    return _evaluate(edge_features, scores, red_pairs, graph, "isolation_forest")


def run_lof(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> dict:
    """Local Outlier Factor: novelty mode, 5% contamination."""
    X, idx = _prepare_features(edge_features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = LocalOutlierFactor(n_neighbors=20, contamination=0.05, novelty=True)
        model.fit(X_scaled)
        scores = -model.score_samples(X_scaled)
    return _evaluate(edge_features, scores, red_pairs, graph, "lof")


def run_ocsvm(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> dict:
    """One-Class SVM: RBF kernel, nu=0.1."""
    X, idx = _prepare_features(edge_features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = OneClassSVM(kernel="rbf", gamma="scale", nu=0.1)
        model.fit(X_scaled)
        scores = -model.decision_function(X_scaled)
    return _evaluate(edge_features, scores, red_pairs, graph, "ocsvm")


def run_elliptic_envelope(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> dict:
    """Elliptic Envelope: 5% contamination."""
    X, idx = _prepare_features(edge_features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = EllipticEnvelope(contamination=0.05, random_state=42)
        model.fit(X_scaled)
        scores = -model.score_samples(X_scaled)
    return _evaluate(edge_features, scores, red_pairs, graph, "elliptic_envelope")


def run_pca_reconstruction(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> dict:
    """PCA reconstruction error: retain 95% variance."""
    X, idx = _prepare_features(edge_features)
    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    model = PCA(n_components=0.95, random_state=42)
    model.fit(X_scaled)
    X_reconstructed = model.inverse_transform(model.transform(X_scaled))
    scores = np.mean((X_scaled - X_reconstructed) ** 2, axis=1)
    return _evaluate(edge_features, scores, red_pairs, graph, "pca_reconstruction")


def run_lanl_baselines(
    edge_features: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    graph,
) -> list[dict]:
    """Run all 5 LANL unsupervised baselines.

    Returns list of result dicts with keys: method_name, auc, recall, fpr, f1.
    """
    baselines = [
        ("Isolation Forest", run_isolation_forest),
        ("LOF", run_lof),
        ("One-Class SVM", run_ocsvm),
        ("Elliptic Envelope", run_elliptic_envelope),
        ("PCA Reconstruction", run_pca_reconstruction),
    ]

    results = []
    for name, fn in baselines:
        try:
            logger.info(f"Running LANL baseline: {name}...")
            result = fn(edge_features, red_pairs, graph)
            results.append(result)
            logger.info(f"  {name}: AUC={result['auc']:.4f}, F1={result['f1']:.4f}")
        except Exception as e:
            logger.warning(f"  {name} failed: {e}")
            continue

    return results
