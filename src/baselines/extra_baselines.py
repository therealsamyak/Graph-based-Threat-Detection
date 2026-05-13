"""Extra ML baselines: LOF, EllipticEnvelope, PCA reconstruction.

Isolated from shared_baselines.py so it can be developed independently of the
main pipeline. Mirrors the same result-dict schema so outputs can be
concatenated with run_baselines() output.
"""

from __future__ import annotations

import logging
import warnings
from concurrent.futures import ProcessPoolExecutor

import numpy as np
from sklearn.covariance import EllipticEnvelope
from sklearn.decomposition import PCA
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
from sklearn.neighbors import LocalOutlierFactor
from sklearn.preprocessing import StandardScaler

logger = logging.getLogger(__name__)


def _prepare_train_test(
    features: np.ndarray, labels: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray] | None:
    normal_mask = labels == 0
    if normal_mask.sum() == 0:
        return None
    scaler = StandardScaler()
    X_train = scaler.fit_transform(features[normal_mask])
    X_test = scaler.transform(features)
    return X_train, X_test, labels


def _scores_to_metrics(method_name: str, y_test: np.ndarray, y_pred: np.ndarray, scores: np.ndarray) -> dict:
    auc = roc_auc_score(y_test, scores) if len(np.unique(y_test)) > 1 else 0.0
    f1 = f1_score(y_test, y_pred, zero_division=0)
    rec = recall_score(y_test, y_pred, zero_division=0)
    prec = precision_score(y_test, y_pred, zero_division=0)
    tn = np.sum((y_test == 0) & (y_pred == 0))
    fp = np.sum((y_test == 0) & (y_pred == 1))
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
    return {
        "method": method_name,
        "auc": round(float(auc), 4),
        "f1": round(float(f1), 4),
        "recall": round(float(rec), 4),
        "fpr": round(float(fpr), 4),
        "precision": round(float(prec), 4),
    }


def _run_lof(args: tuple) -> dict:
    X_train, X_test, y_test, cfg = args
    n_neighbors = cfg.get("n_neighbors", 20)
    contamination = cfg.get("contamination", 0.05)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = LocalOutlierFactor(
            n_neighbors=n_neighbors,
            contamination=contamination,
            novelty=True,
            n_jobs=1,
        )
        model.fit(X_train)
        decision = model.decision_function(X_test)
        preds = model.predict(X_test)
    y_pred = (preds == -1).astype(int)
    return _scores_to_metrics("lof", y_test, y_pred, -decision)


def _run_elliptic_envelope(args: tuple) -> dict:
    X_train, X_test, y_test, cfg = args
    contamination = cfg.get("contamination", 0.05)
    support_fraction = cfg.get("support_fraction", None)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        model = EllipticEnvelope(
            contamination=contamination,
            support_fraction=support_fraction,
            random_state=cfg.get("random_state", 42),
        )
        model.fit(X_train)
        decision = model.decision_function(X_test)
        preds = model.predict(X_test)
    y_pred = (preds == -1).astype(int)
    return _scores_to_metrics("elliptic_envelope", y_test, y_pred, -decision)


def _run_pca_reconstruction(args: tuple) -> dict:
    X_train, X_test, y_test, cfg = args
    n_components = cfg.get("n_components", min(5, X_train.shape[1]))
    contamination = cfg.get("contamination", 0.05)
    n_components = min(n_components, X_train.shape[1])
    model = PCA(n_components=n_components, random_state=cfg.get("random_state", 42))
    model.fit(X_train)
    X_test_proj = model.transform(X_test)
    X_test_recon = model.inverse_transform(X_test_proj)
    errors = np.sum((X_test - X_test_recon) ** 2, axis=1)
    threshold = np.quantile(errors, 1.0 - contamination)
    y_pred = (errors > threshold).astype(int)
    return _scores_to_metrics("pca_reconstruction", y_test, y_pred, errors)


def run_extra_baselines(
    features: np.ndarray, labels: np.ndarray, config: dict | None = None
) -> list[dict]:
    """Train LOF + EllipticEnvelope + PCA on normal data, evaluate on all.

    Same return shape as shared_baselines.run_baselines().
    """
    _cfg = config or {}
    base = _cfg.get("baselines", {})
    lof_cfg = base.get("lof", {})
    ee_cfg = base.get("elliptic_envelope", {})
    pca_cfg = base.get("pca_reconstruction", {})

    prepared = _prepare_train_test(features, labels)
    if prepared is None:
        logger.warning("No normal samples for extra baseline training")
        return []
    X_train, X_test, y_test = prepared
    if len(np.unique(y_test)) < 2:
        logger.warning("Only one class in labels — extra baselines cannot evaluate")
        return []

    jobs = [
        ("lof", _run_lof, (X_train, X_test, y_test, lof_cfg)),
        ("elliptic_envelope", _run_elliptic_envelope, (X_train, X_test, y_test, ee_cfg)),
        ("pca_reconstruction", _run_pca_reconstruction, (X_train, X_test, y_test, pca_cfg)),
    ]

    results: list[dict] = []
    with ProcessPoolExecutor(max_workers=len(jobs)) as pool:
        futures = {name: pool.submit(fn, args) for name, fn, args in jobs}
        for name, fut in futures.items():
            try:
                results.append(fut.result())
            except Exception as e:
                logger.warning(f"{name} failed: {e}")
    return results
