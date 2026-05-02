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

CACHE_DIR = Path("results/cache")


def stream_gz_lines(
    filepath: str,
    columns: list[str],
    max_lines: int | None = None,
) -> Iterator[dict]:
    """Yield parsed lines from a gz file one at a time."""
    with gzip.open(filepath, "rt", encoding="utf-8") as f:
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


def _build_window_intervals(
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


def _time_in_any_window(time: int, windows: list[tuple[int, int]], _starts: list[int] | None = None) -> bool:
    starts = _starts if _starts is not None else [w[0] for w in windows]
    i = bisect.bisect_right(starts, time) - 1
    if i >= 0 and windows[i][0] <= time <= windows[i][1]:
        return True
    return False


def extract_windows(
    gz_path: str,
    columns: list[str],
    windows: list[tuple[int, int]],
    max_events: int | None = None,
    numeric_cols: set[str] | None = None,
) -> pd.DataFrame:
    """Stream through gz file, collecting events within time windows.

    Seeks to the first window start, reads until past the last window end.
    max_events limits how many matching events to collect (for testing).
    """
    if not windows:
        return pd.DataFrame(columns=columns)

    first_window_start = windows[0][0]
    last_window_end = windows[-1][1]

    rows = []
    past_start = False
    _starts = [w[0] for w in windows]

    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for line in f:
            parts = line.strip().split(",")
            if len(parts) != len(columns):
                continue

            time_val = int(parts[0])

            if not past_start:
                if time_val < first_window_start:
                    continue
                past_start = True

            if time_val > last_window_end:
                break

            if _time_in_any_window(time_val, windows, _starts):
                rows.append(dict(zip(columns, parts)))
                if max_events is not None and len(rows) >= max_events:
                    break

    if not rows:
        return pd.DataFrame(columns=columns)

    df = pd.DataFrame(rows)
    for c in (numeric_cols or set()):
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.replace("?", pd.NA)
    df = df.dropna(subset=["time"])
    return df.reset_index(drop=True)


def load_lanl_data(
    data_dir: str,
    window_seconds: int = 3600,
    max_events: int | None = None,
) -> dict[str, pd.DataFrame]:
    """Load auth + flows + redteam data with time-window extraction.

    Seeks directly to window regions in gz files — does not read entire file.

    Args:
        data_dir: Path to LANL-2015 data directory.
        window_seconds: Half-window size (±N seconds) around each red team event.
        max_events: Max events to collect per source (for testing).

    Returns:
        Dict with 'auth', 'flows', 'redteam' DataFrames.
    """
    data_path = Path(data_dir)
    cache_key = f"w{window_seconds}_me{max_events or 'full'}"
    auth_cache = CACHE_DIR / f"auth_{cache_key}.parquet"
    flow_cache = CACHE_DIR / f"flows_{cache_key}.parquet"

    redteam_df = load_redteam(str(data_path / "redteam.txt.gz"))

    if auth_cache.exists() and flow_cache.exists():
        auth_df = pd.read_parquet(auth_cache)
        flow_df = pd.read_parquet(flow_cache)
        return {"auth": auth_df, "flows": flow_df, "redteam": redteam_df}

    windows = _build_window_intervals(redteam_df, window_seconds)

    auth_df = extract_windows(
        str(data_path / "auth.txt.gz"), AUTH_COLUMNS, windows, max_events, AUTH_NUMERIC
    )
    flow_df = extract_windows(
        str(data_path / "flows.txt.gz"), FLOW_COLUMNS, windows, max_events, FLOW_NUMERIC
    )

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    if not auth_df.empty:
        auth_df.to_parquet(auth_cache, index=False)
    if not flow_df.empty:
        flow_df.to_parquet(flow_cache, index=False)

    return {"auth": auth_df, "flows": flow_df, "redteam": redteam_df}
