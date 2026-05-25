"""Shared pipeline cache: graphs, features, redteam data, top features."""

from __future__ import annotations

import json
import logging
import pickle
from datetime import datetime
from pathlib import Path

import pandas as pd

from src.csv_split import csv_exists, load_csv_merged, save_csv_split

logger = logging.getLogger(__name__)

CACHE_ROOT = Path(".cache/pipeline")


def cache_dir(max_events: int | None) -> Path:
    """Return cache directory for given max_events."""
    tag = str(max_events) if max_events is not None else "full"
    return CACHE_ROOT / tag


def _get_data_mtime(data_dir: str) -> float:
    """Latest mtime of data files for cache validation."""
    data_path = Path(data_dir)
    mtimes: list[float] = []
    for name in ["auth.txt", "auth.txt.gz", "flows.txt", "flows.txt.gz", "redteam.txt"]:
        p = data_path / name
        if p.exists():
            mtimes.append(p.stat().st_mtime)
    return max(mtimes) if mtimes else 0.0


def prepare_cache_dir(max_events: int | None) -> Path:
    """Create cache dir and return it."""
    cdir = cache_dir(max_events)
    cdir.mkdir(parents=True, exist_ok=True)
    # Write metadata
    meta = {
        "created_at": datetime.now().isoformat(),
        "max_events": max_events,
    }
    (cdir / "metadata.json").write_text(json.dumps(meta, indent=2))
    return cdir


# ── Redteam ──────────────────────────────────────────────────────────


def save_redteam(
    cache_path: Path,
    rt: pd.DataFrame,
    red_pairs: set[tuple[str, str]],
    windows: list[tuple[int, int]],
) -> None:
    """Save redteam data to cache."""
    rt_dir = cache_path / "redteam"
    rt_dir.mkdir(parents=True, exist_ok=True)
    rt.to_csv(rt_dir / "redteam_events.csv", index=False)
    with open(rt_dir / "redteam_pairs.json", "w") as f:
        json.dump([{"src": s, "dst": d} for s, d in sorted(red_pairs)], f, indent=2)
    with open(rt_dir / "window_intervals.json", "w") as f:
        json.dump([{"start": s, "end": e} for s, e in windows], f, indent=2)
    logger.info(f"  Saved redteam data to {rt_dir}")


def load_redteam(cache_path: Path) -> tuple[pd.DataFrame, set, list]:
    """Load redteam data from cache. Raises FileNotFoundError if missing."""
    rt_dir = cache_path / "redteam"
    rt = pd.read_csv(rt_dir / "redteam_events.csv")
    with open(rt_dir / "redteam_pairs.json") as f:
        red_pairs = {((p["src"], p["dst"])) for p in json.load(f)}
    with open(rt_dir / "window_intervals.json") as f:
        windows = [(w["start"], w["end"]) for w in json.load(f)]
    logger.info(f"  Loaded redteam from cache: {len(rt)} events, {len(red_pairs)} pairs")
    return rt, red_pairs, windows


def has_redteam(cache_path: Path) -> bool:
    rt_dir = cache_path / "redteam"
    return (
        (rt_dir / "redteam_events.csv").exists()
        and (rt_dir / "redteam_pairs.json").exists()
        and (rt_dir / "window_intervals.json").exists()
    )


# ── Graph pickle ─────────────────────────────────────────────────────


def save_graph(
    cache_path: Path,
    variant: str,
    *,
    graph,
    build_time: float,
    total_events: int,
    data_mtime: float,
    max_events: int | None,
) -> None:
    """Save graph pickle to cache variant dir."""
    vdir = cache_path / variant
    vdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "graph": graph,
        "build_time": build_time,
        "total_events": total_events,
        "data_mtime": data_mtime,
        "max_events": max_events,
    }
    with open(vdir / "graph.pkl", "wb") as f:
        pickle.dump(payload, f)
    logger.info(f"  Saved graph pickle to {vdir / 'graph.pkl'}")


def load_graph(
    cache_path: Path,
    variant: str,
    *,
    data_dir: str | None = None,
    max_events: int | None = None,
) -> dict | None:
    """Load graph pickle from cache. Returns None if missing/invalid."""
    pkl_path = cache_path / variant / "graph.pkl"
    if not pkl_path.exists():
        return None
    try:
        with open(pkl_path, "rb") as f:
            cached = pickle.load(f)
    except Exception:
        logger.warning(f"  Failed to load graph cache for '{variant}'")
        return None

    # Validate max_events match
    if max_events is not None and cached.get("max_events") != max_events:
        return None

    # Validate data mtime if data_dir provided
    if data_dir is not None:
        current_mtime = _get_data_mtime(data_dir)
        if cached.get("data_mtime") != current_mtime:
            return None

    return cached


# ── Features ─────────────────────────────────────────────────────────


def save_features(
    cache_path: Path,
    variant: str,
    *,
    edge_features: pd.DataFrame,
    node_features,
    graph_features: dict,
    graph_edges: pd.DataFrame,
) -> None:
    """Save feature CSVs to cache variant dir."""
    vdir = cache_path / variant
    vdir.mkdir(parents=True, exist_ok=True)
    save_csv_split(edge_features, vdir / "edge_features.csv")
    graph_edges.to_csv(vdir / "graph_edges.csv", index=False)
    if node_features is not None:
        node_features.to_csv(vdir / "node_features.csv")
    with open(vdir / "graph_features.json", "w") as f:
        json.dump(graph_features, f, indent=2)
    logger.info(f"  Saved features to {vdir}")


def load_features(cache_path: Path, variant: str) -> dict | None:
    """Load feature CSVs from cache. Returns None if missing."""
    vdir = cache_path / variant
    ef_path = vdir / "edge_features.csv"
    ge_path = vdir / "graph_edges.csv"
    if not csv_exists(ef_path) or not ge_path.exists():
        return None

    edge_features = load_csv_merged(ef_path, index_col=0)
    pd.read_csv(ge_path)  # validate file is readable

    node_features = None
    nf_path = vdir / "node_features.csv"
    if nf_path.exists():
        node_features = pd.read_csv(nf_path, index_col=0)

    graph_features = {}
    gf_path = vdir / "graph_features.json"
    if gf_path.exists():
        with open(gf_path) as f:
            graph_features = json.load(f)

    return {
        "edge_features": edge_features,
        "node_features": node_features,
        "graph_features": graph_features,
    }


# ── Top features ─────────────────────────────────────────────────────


def save_top_features(
    cache_path: Path, variant: str, features: list[str], count: int
) -> None:
    """Save top_features.json."""
    vdir = cache_path / variant
    vdir.mkdir(parents=True, exist_ok=True)
    payload = {
        "features": features,
        "count": count,
        "source": "audit",
    }
    (vdir / "top_features.json").write_text(json.dumps(payload, indent=2))
    logger.info(f"  Saved top_features.json to {vdir}")


def load_top_features(cache_path: Path, variant: str) -> list[str] | None:
    """Load top features list. Returns None if missing."""
    path = cache_path / variant / "top_features.json"
    if not path.exists():
        return None
    with open(path) as f:
        data = json.load(f)
    return data.get("features")


# ── Completeness check ───────────────────────────────────────────────


def has_complete_cache(cache_path: Path) -> bool:
    """Check if all 3 variants + redteam data exist in cache."""
    if not has_redteam(cache_path):
        return False
    for variant in ("auth_only", "combined", "flow_only"):
        vdir = cache_path / variant
        if not (vdir / "graph.pkl").exists():
            return False
        if not csv_exists(vdir / "edge_features.csv"):
            return False
        if not (vdir / "top_features.json").exists():
            return False
    return True
