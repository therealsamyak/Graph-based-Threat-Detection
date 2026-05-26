"""Data loading helpers for figure generation."""

# pyright: reportMissingTypeArgument=false

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any, cast

import pandas as pd
from sklearn.metrics import roc_curve

from src.figures.style import logger


def _resolve_baseline_run_dir(baselines_dir: Path) -> Path | None:
    if not baselines_dir.exists():
        return None
    direct_summary = baselines_dir / "summary.json"
    if direct_summary.exists():
        return baselines_dir
    run_dirs = sorted(p for p in baselines_dir.iterdir() if p.is_dir())
    for run_dir in run_dirs:
        if (run_dir / "summary.json").exists():
            return run_dir
    return None


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    return df


def load_metrics(results_dir: Path) -> pd.DataFrame | None:
    path = results_dir / "metrics.csv"
    if not path.exists():
        logger.warning("metrics.csv not found: %s", path)
        return None
    df = pd.read_csv(path)
    logger.info("Loaded metrics: %d rows from %s", len(df), path)
    return df


def load_run_metadata(results_dir: Path) -> dict | None:
    path = results_dir / "pipeline_run.json"
    if not path.exists():
        logger.warning("pipeline_run.json not found: %s", path)
        return None
    with open(path) as f:
        data = json.load(f)
    logger.info("Loaded run metadata from %s", path)
    return data


def _load_json_object(path: Path) -> dict[str, Any]:
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        return data
    return {"value": data}


def load_feature_audit(audit_dir: Path) -> dict[str, Any] | None:
    path = audit_dir / "feature_audit_results.json"
    if path.exists():
        data = _load_json_object(path)
        logger.info("Loaded feature audit from %s", path)
        return data

    per_variant: dict[str, dict[str, Any]] = {}
    for variant_dir in sorted(p for p in audit_dir.iterdir() if p.is_dir()):
        variant_path = variant_dir / "feature_audit_results.json"
        if variant_path.exists():
            per_variant[variant_dir.name] = _load_json_object(variant_path)

    if per_variant:
        logger.info("Loaded feature audit for %d variants from %s", len(per_variant), audit_dir)
        return {"per_variant": per_variant}

    combined_path = audit_dir / "combined" / "feature_audit_results.json"
    logger.warning("feature_audit_results.json not found: %s (also tried %s)", path, combined_path)
    return None


def load_analysis_results(analysis_dir: Path) -> dict[str, Any] | None:
    aggregated: dict[str, Any] = {}

    json_files = sorted(analysis_dir.glob("*.json"))
    for jf in json_files:
        aggregated[jf.stem] = _load_json_object(jf)

    per_variant: dict[str, dict[str, Any]] = {}
    for variant_dir in sorted(p for p in analysis_dir.iterdir() if p.is_dir()):
        variant_files = sorted(variant_dir.glob("*.json"))
        if not variant_files:
            continue
        per_variant[variant_dir.name] = {
            jf.stem: _load_json_object(jf)
            for jf in variant_files
        }

    if per_variant:
        aggregated["per_variant"] = per_variant
        if not json_files and "combined" in per_variant:
            aggregated.update(per_variant["combined"])
        total_files = sum(len(v) for v in per_variant.values()) + len(json_files)
        logger.info(
            "Loaded %d analysis files for %d variants from %s",
            total_files,
            len(per_variant),
            analysis_dir,
        )
        return aggregated

    if json_files:
        logger.info("Loaded %d analysis files from %s", len(json_files), analysis_dir)
        return aggregated

    combined_dir = analysis_dir / "combined"
    combined_files = sorted(combined_dir.glob("*.json")) if combined_dir.is_dir() else []
    if combined_files:
        combined_data = {jf.stem: _load_json_object(jf) for jf in combined_files}
        combined_data["per_variant"] = {"combined": combined_data.copy()}
        logger.info("Loaded %d analysis files from %s", len(combined_files), combined_dir)
        return combined_data

    logger.warning("No JSON files found in %s (or its variant subdirs)", analysis_dir)
    return None


def load_per_method_details(results_dir: Path) -> dict:
    path = results_dir / "per_method_details.json"
    if not path.exists():
        logger.warning("per_method_details.json not found: %s", path)
        return {}
    with open(path) as f:
        raw = json.load(f)
    per_variant: dict[str, dict] = {}
    for key, metrics in raw.items():
        if not isinstance(key, str) or not isinstance(metrics, dict):
            continue
        variant = key.split("/", 1)[1] if "/" in key else key
        per_variant[variant] = metrics
    logger.info("Loaded per-method details from %s (%d variants)", path, len(per_variant))
    return per_variant


def load_baseline_summary(baselines_dir: Path) -> dict:
    run_dir = _resolve_baseline_run_dir(baselines_dir)
    if run_dir is None:
        logger.warning("baseline summary run dir not found under %s", baselines_dir)
        return {}
    path = run_dir / "summary.json"
    with open(path) as f:
        data = json.load(f)
    per_variant = data.get("per_variant_summary", data)
    if not isinstance(per_variant, dict):
        logger.warning("Invalid baseline summary format in %s", path)
        return {}
    normalized: dict[str, dict] = {}
    for variant, methods in per_variant.items():
        if isinstance(methods, dict):
            normalized[str(variant)] = methods
    logger.info("Loaded baseline summary from %s (%d variants)", path, len(normalized))
    return normalized


def load_baseline_edge_scores(baselines_dir: Path, variant: str) -> pd.DataFrame | None:
    run_dir = _resolve_baseline_run_dir(baselines_dir)
    if run_dir is None:
        return None
    path = run_dir / variant / "edge_scores.csv"
    if not path.exists():
        logger.warning("baseline edge_scores.csv not found: %s", path)
        return None
    df = pd.read_csv(path, low_memory=False)
    df = _normalize_columns(df)
    logger.info("Loaded baseline edge scores: %d rows from %s", len(df), path)
    return df


def build_method_variant_matrix(per_method_details: dict, baseline_summary: dict) -> pd.DataFrame:
    cols = [
        "method",
        "variant",
        "auc",
        "f1",
        "recall",
        "fpr",
        "precision",
        "latency",
        "throughput",
        "num_detected_pairs",
        "num_redteam_pairs",
    ]
    rows: list[dict] = []

    for variant, metrics in per_method_details.items():
        if not isinstance(metrics, dict):
            continue
        rows.append(
            {
                "method": "graph_based",
                "variant": variant,
                "auc": metrics.get("auc"),
                "f1": metrics.get("f1"),
                "recall": metrics.get("recall"),
                "fpr": metrics.get("fpr"),
                "precision": metrics.get("precision"),
                "latency": metrics.get("latency"),
                "throughput": metrics.get("throughput"),
                "num_detected_pairs": metrics.get("anomalous_pairs"),
                "num_redteam_pairs": metrics.get("rt_pairs_in_graph"),
            }
        )

    for variant, methods in baseline_summary.items():
        if not isinstance(methods, dict):
            continue
        for method in ("one_class_svm", "isolation_forest"):
            metrics = methods.get(method, {})
            if not isinstance(metrics, dict):
                metrics = {}
            rows.append(
                {
                    "method": method,
                    "variant": variant,
                    "auc": metrics.get("auc"),
                    "f1": metrics.get("f1"),
                    "recall": metrics.get("recall"),
                    "fpr": metrics.get("fpr"),
                    "precision": metrics.get("precision"),
                    "latency": metrics.get("latency"),
                    "throughput": metrics.get("throughput"),
                    "num_detected_pairs": metrics.get("num_detected_pairs"),
                    "num_redteam_pairs": metrics.get("num_redteam_pairs"),
                }
            )

    matrix = pd.DataFrame(rows, columns=cols)
    if not matrix.empty:
        matrix = matrix.sort_values(["variant", "method"]).reset_index(drop=True)
    return matrix


def build_method_variant_roc_data(baselines_dir: Path) -> dict[tuple[str, str], tuple[Any, Any]]:
    run_dir = _resolve_baseline_run_dir(baselines_dir)
    if run_dir is None:
        return {}

    roc_data: dict[tuple[str, str], tuple[Any, Any]] = {}
    for variant_dir in sorted(p for p in run_dir.iterdir() if p.is_dir() and (p / "edge_scores.csv").exists()):
        variant = variant_dir.name
        df = load_baseline_edge_scores(run_dir, variant)
        if df is None:
            continue
        label_col = "label" if "label" in df.columns else None
        if label_col is None:
            continue

        method_score_cols = {
            "one_class_svm": ["one_class_svm_score", "ocsvm_score", "svm_score"],
            "isolation_forest": ["isolation_forest_score", "if_score", "isoforest_score"],
        }
        y_true = cast(pd.Series, pd.to_numeric(df[label_col], errors="coerce"))

        for method, candidates in method_score_cols.items():
            score_col = next((c for c in candidates if c in df.columns), None)
            if score_col is None:
                continue
            y_score = cast(pd.Series, pd.to_numeric(df[score_col], errors="coerce"))
            valid = cast(pd.Series, y_true.notna() & y_score.notna())
            y_true_valid = cast(pd.Series, y_true[valid])
            if valid.sum() == 0 or y_true_valid.nunique() < 2:
                continue
            fpr, tpr, _ = roc_curve(y_true_valid, y_score[valid])
            roc_data[(method, variant)] = (fpr, tpr)

    return roc_data


def _variant_data_dir(results_dir: Path, variant: str) -> Path | None:
    for candidate in (results_dir / variant, results_dir / "LANL-2015" / variant):
        if candidate.is_dir():
            return candidate
    return None


def _load_variant_graph_edges(results_dir: Path, variant: str) -> pd.DataFrame | None:
    variant_dir = _variant_data_dir(results_dir, variant)
    if variant_dir is None:
        return None
    edges_path = variant_dir / "graph_edges.csv"
    if not edges_path.exists():
        return None
    return pd.read_csv(edges_path, low_memory=False)


def _coerce_float(value: object) -> float | None:
    try:
        numeric = float(str(value))
    except (TypeError, ValueError):
        return None
    return numeric if math.isfinite(numeric) else None


def _with_graph_edge_context(results_dir: Path, variant: str, scores_df: pd.DataFrame) -> pd.DataFrame:
    if "edge_index" not in scores_df.columns:
        return scores_df

    edges_df = _load_variant_graph_edges(results_dir, variant)
    if edges_df is None or edges_df.empty:
        return scores_df

    edge_context = edges_df.reset_index().rename(columns={"index": "edge_index"})
    context_cols = [
        c
        for c in ("edge_index", "src", "dst", "type", "time", "first_time", "last_time")
        if c in edge_context.columns
    ]
    return scores_df.merge(edge_context[context_cols], on="edge_index", how="left")


def _redteam_edge_mask(edge_df: pd.DataFrame, rt_df: pd.DataFrame | None) -> pd.Series:
    if rt_df is None or rt_df.empty:
        return pd.Series(False, index=edge_df.index)
    if not {"src", "dst"}.issubset(edge_df.columns):
        return pd.Series(False, index=edge_df.index)
    if not {"src_comp", "dst_comp"}.issubset(rt_df.columns):
        return pd.Series(False, index=edge_df.index)

    has_rt_time = "time" in rt_df.columns
    rt_by_pair: dict[tuple[str, str], list[float]] = {}
    rt_pairs: set[tuple[str, str]] = set()
    rt_times = list(rt_df["time"]) if has_rt_time else [None] * len(rt_df)
    for src_value, dst_value, time_raw in zip(rt_df["src_comp"], rt_df["dst_comp"], rt_times):
        pair = (str(src_value), str(dst_value))
        rt_pairs.add(pair)
        if has_rt_time:
            time_value = _coerce_float(time_raw)
            if time_value is not None:
                rt_by_pair.setdefault(pair, []).append(time_value)

    use_interval = {"first_time", "last_time"}.issubset(edge_df.columns) and bool(rt_by_pair)
    values: list[bool] = []
    if use_interval:
        for src_value, dst_value, start_raw, end_raw in zip(edge_df["src"], edge_df["dst"], edge_df["first_time"], edge_df["last_time"]):
            pair = (str(src_value), str(dst_value))
            times = rt_by_pair.get(pair, [])
            if not times:
                values.append(False)
                continue
            start = _coerce_float(start_raw)
            end = _coerce_float(end_raw)
            if start is None or end is None:
                values.append(True)
                continue
            values.append(any(start <= t <= end for t in times))
        return pd.Series(values, index=edge_df.index)

    values = [(str(src_value), str(dst_value)) in rt_pairs for src_value, dst_value in zip(edge_df["src"], edge_df["dst"])]
    return pd.Series(values, index=edge_df.index)


def _with_redteam_labels(results_dir: Path, edge_df: pd.DataFrame) -> pd.DataFrame:
    if any(c in edge_df.columns for c in ("is_redteam", "red_team", "redteam", "label")):
        return edge_df

    labeled = edge_df.copy()
    mask = _redteam_edge_mask(labeled, load_redteam_events(results_dir))
    labeled["is_redteam"] = mask.astype(int)
    logger.info("Labeled %d red-team edge scores from graph/red-team context", int(mask.sum()))
    return labeled


def load_edge_scores(results_dir: Path, variant: str) -> pd.DataFrame | None:
    for candidate in (results_dir / variant, results_dir / "LANL-2015" / variant):
        path = candidate / "edge_scores.csv"
        if path.exists():
            df = pd.read_csv(path, low_memory=False)
            df = _with_graph_edge_context(results_dir, variant, df)
            df = _with_redteam_labels(results_dir, df)
            logger.info("Loaded edge scores: %d rows from %s", len(df), path)
            return df
    logger.warning("edge_scores.csv not found for variant '%s' under %s", variant, results_dir)
    return None


def load_redteam_events(results_dir: Path) -> pd.DataFrame | None:
    for candidate in (
        results_dir / "redteam" / "redteam_events.csv",
        results_dir / "LANL-2015" / "redteam" / "redteam_events.csv",
    ):
        if candidate.exists():
            df = pd.read_csv(candidate, low_memory=False)
            logger.info("Loaded redteam events: %d rows from %s", len(df), candidate)
            return df
    logger.warning("redteam_events.csv not found under %s", results_dir)
    return None


def load_graph_data(results_dir: Path, variant: str) -> tuple | None:
    for candidate in (results_dir / variant, results_dir / "LANL-2015" / variant):
        edges_path = candidate / "graph_edges.csv"
        nodes_path = candidate / "node_features.csv"
        if edges_path.exists():
            edges_df = pd.read_csv(edges_path, low_memory=False)
            nodes_df = pd.read_csv(nodes_path, low_memory=False) if nodes_path.exists() else None
            logger.info("Loaded graph data for variant '%s': %d edges", variant, len(edges_df))
            return (edges_df, nodes_df)
    logger.warning("graph_edges.csv not found for variant '%s' under %s", variant, results_dir)
    return None
