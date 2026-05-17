"""Streaming gz reader and window extraction for LANL-2015 data."""

from __future__ import annotations

import bisect
import gzip
from collections.abc import Iterator
from pathlib import Path

import pandas as pd

AUTH_COLUMNS = [
    "time", "src_user", "dst_user", "src_comp", "dst_comp",
    "auth_type", "logon_type", "auth_orientation", "success",
]
FLOW_COLUMNS = [
    "time", "duration", "src_comp", "src_port", "dst_comp",
    "dst_port", "protocol", "pkt_count", "byte_count",
]
REDTEAM_COLUMNS = ["time", "user", "src_comp", "dst_comp"]

AUTH_NUMERIC = {"time"}
FLOW_NUMERIC = {"time", "duration", "src_port", "dst_port", "protocol", "pkt_count", "byte_count"}
REDTEAM_NUMERIC = {"time"}


def _open_auto(filepath: str):
    """Open a file as gzip if it ends with .gz, otherwise as plain text."""
    if filepath.endswith(".gz"):
        return gzip.open(filepath, "rt", encoding="utf-8")
    return open(filepath, "r", encoding="utf-8")


def stream_gz_lines(
    filepath: str,
    columns: list[str],
    max_lines: int | None = None,
) -> Iterator[dict]:
    """Yield parsed lines from a gz or plain text file one at a time."""
    with _open_auto(filepath) as f:
        for i, line in enumerate(f):
            if max_lines is not None and i >= max_lines:
                break
            parts = line.strip().split(",")
            if len(parts) != len(columns):
                continue
            yield dict(zip(columns, parts))


def load_redteam(path: str) -> pd.DataFrame:
    """Load and parse redteam.txt.gz (small file, safe to load fully)."""
    rows = list(stream_gz_lines(path, REDTEAM_COLUMNS))
    df = pd.DataFrame(rows)
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.dropna(subset=["time"])
    df = df.sort_values("time").reset_index(drop=True)
    return df


def build_window_intervals(
    redteam_df: pd.DataFrame, window_seconds: int
) -> list[tuple[int, int]]:
    if redteam_df.empty:
        return []
    intervals = []
    for t in redteam_df["time"]:
        t = int(t)
        intervals.append((t - window_seconds, t + window_seconds))
    intervals.sort()
    merged = [intervals[0]]
    for start, end in intervals[1:]:
        if start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def time_in_any_window(time: int, windows: list[tuple[int, int]], _starts: list[int] | None = None) -> bool:
    starts = _starts if _starts is not None else [w[0] for w in windows]
    i = bisect.bisect_right(starts, time) - 1
    if i >= 0 and windows[i][0] <= time <= windows[i][1]:
        return True
    return False
