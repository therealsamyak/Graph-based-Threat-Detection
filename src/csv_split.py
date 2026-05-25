"""Split/merge large CSVs to stay under GitHub's 100 MB file-size limit.

Naming convention for a base path like ``edge_features.csv``:
  - ``edge_features_pt1.csv``
  - ``edge_features_pt2.csv``

All downstream code calls :func:`load_csv_merged` which transparently
reassembles the DataFrame regardless of whether it was split.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

# Safety margin below GitHub's 100 MB hard limit (in bytes).
_MAX_BYTES = 90 * 10**6  # 90 MB


def _split_paths(base: Path) -> list[Path]:
    """Return ``[base_pt1.csv, base_pt2.csv]``."""
    stem = base.stem
    suffix = base.suffix
    parent = base.parent
    return [parent / f"{stem}_pt1{suffix}", parent / f"{stem}_pt2{suffix}"]


def save_csv_split(df: pd.DataFrame, base_path: Path, **csv_kwargs) -> None:
    """Write *df* to CSV, splitting into two parts if it would exceed 90 MB.

    If the resulting CSV would be <= 90 MB a single file is written at
    *base_path*.  Otherwise it is split into ``_pt1`` / ``_pt2`` files
    (any existing single-file version is removed, and vice-versa).
    """
    # Estimate final size via first 5 000 rows.
    sample_csv = df.head(min(5_000, len(df))).to_csv(**csv_kwargs)
    est_bytes = len(sample_csv.encode()) / min(5_000, len(df)) * len(df)

    if est_bytes <= _MAX_BYTES:
        # Clean up stale split files if they exist.
        for p in _split_paths(base_path):
            p.unlink(missing_ok=True)
        df.to_csv(base_path, **csv_kwargs)
        return

    mid = len(df) // 2
    p1, p2 = _split_paths(base_path)
    # Remove stale single file.
    base_path.unlink(missing_ok=True)
    df.iloc[:mid].to_csv(p1, **csv_kwargs)
    df.iloc[mid:].to_csv(p2, **csv_kwargs)
    logger.info(
        f"  Split CSV into 2 parts: {p1.name} + {p2.name} "
        f"(~{est_bytes / 1e6:.0f} MB total)"
    )


def load_csv_merged(base_path: Path, **csv_kwargs) -> pd.DataFrame:
    """Load a CSV that may have been split into ``_pt1`` / ``_pt2`` parts.

    Falls back to the single file when split files are absent.
    """
    p1, p2 = _split_paths(base_path)
    if p1.exists() and p2.exists():
        df1 = pd.read_csv(p1, **csv_kwargs)
        df2 = pd.read_csv(p2, **csv_kwargs)
        return pd.concat([df1, df2], ignore_index=True)
    if p1.exists():
        return pd.read_csv(p1, **csv_kwargs)
    return pd.read_csv(base_path, **csv_kwargs)


def csv_exists(base_path: Path) -> bool:
    """True when either the single file or its split pair exists."""
    if base_path.exists():
        return True
    p1, _ = _split_paths(base_path)
    return p1.exists()
