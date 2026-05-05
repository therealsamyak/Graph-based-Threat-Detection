"""Streaming graph construction: build igraph incrementally from gz event streams."""

from __future__ import annotations

import gzip
import logging

import igraph as ig
import pandas as pd

from src.data.lanl import time_in_any_window

logger = logging.getLogger(__name__)


class StreamingGraphBuilder:
    """Incrementally builds an igraph from streamed events.

    Call feed_auth_event() / feed_flow_event() for each row,
    then call build() to get the final graph.
    """

    def __init__(self) -> None:
        self._g = ig.Graph(directed=True)
        self._node_set: set[str] = set()
        self._edge_map: dict[tuple[str, str], dict] = {}

    def _ensure_node(self, name: str, node_type: str) -> None:
        if name not in self._node_set:
            is_machine = "$" in name.split("@")[0] if "@" in name else name.endswith("$")
            self._g.add_vertex(name, node_type=node_type, is_machine=is_machine)
            self._node_set.add(name)

    def _add_edge(self, src: str, dst: str, attrs: dict, src_type: str = "computer", dst_type: str = "computer") -> None:
        self._ensure_node(src, src_type)
        self._ensure_node(dst, dst_type)
        key = (src, dst)
        if key in self._edge_map:
            self._edge_map[key]["weight"] += 1
            existing_time = self._edge_map[key].get("first_time", self._edge_map[key].get("time", 0))
            self._edge_map[key]["last_time"] = attrs.get("time", 0)
            self._edge_map[key]["first_time"] = existing_time
        else:
            self._edge_map[key] = {**attrs, "weight": 1, "first_time": attrs.get("time", 0)}

    def feed_auth_event(self, row: dict) -> None:
        src_c = row.get("src_comp")
        dst_c = row.get("dst_comp")
        src_u = row.get("src_user")
        dst_u = row.get("dst_user")
        if pd.isna(src_c) or pd.isna(dst_c):
            return

        base = {
            "type": "auth",
            "auth_type": row.get("auth_type", ""),
            "logon_type": row.get("logon_type", ""),
            "auth_orientation": row.get("auth_orientation", ""),
            "success": row.get("success", ""),
            "time": float(row.get("time", 0)),
        }
        self._add_edge(str(src_c), str(dst_c), base)

        if not pd.isna(src_u) and not pd.isna(dst_u):
            user_edge_attrs = {
                "type": "auth",
                "auth_type": row.get("auth_type", ""),
                "logon_type": row.get("logon_type", ""),
                "auth_orientation": row.get("auth_orientation", ""),
                "success": row.get("success", ""),
                "time": float(row.get("time", 0)),
            }
            self._add_edge(str(src_u), str(dst_u), user_edge_attrs, src_type="user", dst_type="user")

    def feed_flow_event(self, row: dict) -> None:
        src_c = row.get("src_comp")
        dst_c = row.get("dst_comp")
        if pd.isna(src_c) or pd.isna(dst_c):
            return

        base = {
            "type": "flow",
            "protocol": row.get("protocol", ""),
            "src_port": row.get("src_port", ""),
            "dst_port": row.get("dst_port", ""),
            "pkt_count": row.get("pkt_count", 0),
            "byte_count": row.get("byte_count", 0),
            "duration": row.get("duration", 0),
            "time": float(row.get("time", 0)),
        }
        self._add_edge(str(src_c), str(dst_c), base)

    def build(self) -> ig.Graph:
        for (src, dst), attrs in self._edge_map.items():
            self._g.add_edge(src, dst, **attrs)
        return self._g


def stream_gz_to_graph(
    gz_path: str,
    columns: list[str],
    windows: list[tuple[int, int]],
    numeric_cols: set[str],
    graph: StreamingGraphBuilder,
    feed_fn,
    progress_every: int = 500000,
    max_events: int | None = None,
) -> int:
    """Stream gz file through windows, feed events to graph, return row count."""
    if not windows:
        return 0

    first_start = windows[0][0]
    last_end = windows[-1][1]

    count = 0
    past_start = False
    _starts = [w[0] for w in windows]

    with gzip.open(gz_path, "rt", encoding="utf-8") as f:
        for raw_line in f:
            parts = raw_line.strip().split(",")
            if len(parts) != len(columns):
                continue

            time_val = int(parts[0])

            if not past_start:
                if time_val < first_start:
                    continue
                past_start = True

            if time_val > last_end:
                break

            if not time_in_any_window(time_val, windows, _starts):
                continue

            row = dict(zip(columns, parts))
            for c in numeric_cols:
                if c in row:
                    try:
                        row[c] = float(row[c])
                    except (ValueError, TypeError):
                        pass

            feed_fn(row)
            count += 1
            if max_events is not None and count >= max_events:
                break
            if count % progress_every == 0:
                logger.info(f"  {gz_path}: {count:,} events processed...")

    return count
