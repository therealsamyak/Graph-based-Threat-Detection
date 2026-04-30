"""Streaming pipeline: build graph directly from gz stream, never materialize full DataFrames.

Streams auth.txt.gz and flows.txt.gz line-by-line through the time windows,
adds edges to an igraph incrementally, and discards raw rows immediately.
"""

from __future__ import annotations

import gzip
import json
import logging
import time
from pathlib import Path

import igraph as ig
import numpy as np
import pandas as pd

from src.data_loader import (
    AUTH_COLUMNS,
    AUTH_NUMERIC,
    FLOW_COLUMNS,
    FLOW_NUMERIC,
    _build_window_intervals,
    _time_in_any_window,
    load_redteam,
)

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

    def _add_edge(self, src: str, dst: str, attrs: dict) -> None:
        self._ensure_node(src, "computer")
        self._ensure_node(dst, "computer")
        key = (src, dst)
        if key in self._edge_map:
            self._edge_map[key]["weight"] += 1
            self._edge_map[key]["time"] = attrs.get("time", 0)
        else:
            self._edge_map[key] = {**attrs, "weight": 1}

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
            self._ensure_node(str(src_u), "user")
            self._ensure_node(str(dst_u), "user")

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


def _stream_gz_to_graph(
    gz_path: str,
    columns: list[str],
    windows: list[tuple[int, int]],
    numeric_cols: set[str],
    graph: StreamingGraphBuilder,
    feed_fn,
    progress_every: int = 500000,
) -> int:
    """Stream gz file through windows, feed events to graph, return row count."""
    if not windows:
        return 0

    first_start = windows[0][0]
    last_end = windows[-1][1]

    count = 0
    past_start = False

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

            if not _time_in_any_window(time_val, windows):
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
            if count % progress_every == 0:
                logger.info(f"  {gz_path}: {count:,} events processed...")

    return count


def run_streaming_experiment(
    data_dir: str = "data/LANL-Dataset-2015",
    window_seconds: int = 3600,
    dapt_dir: str = "data/DAPT2020",
) -> list[dict]:
    """Run full experiment using streaming graph construction.

    Streams auth + flow gz files through time windows,
    builds graph incrementally (no DataFrame materialization),
    runs scoring and detection, then discards graph.
    """
    data_path = Path(data_dir)
    all_results: list[dict] = []

    # Load red team (tiny file)
    rt = load_redteam(str(data_path / "redteam.txt.gz"))
    red_pairs = set(zip(rt["src_comp"].astype(str), rt["dst_comp"].astype(str)))
    windows = _build_window_intervals(rt, window_seconds)
    logger.info(f"Red team: {len(rt)} events, {len(windows)} merged windows")

    # Stream both files into graph, then score, then discard
    for method_name, feed_auth, feed_flow in [
        ("flow_only", None, True),
        ("auth_only", True, None),
        ("combined", True, True),
    ]:
        logger.info(f"Streaming + building: {method_name}")
        t0 = time.perf_counter()

        graph = StreamingGraphBuilder()

        if feed_auth:
            n_auth = _stream_gz_to_graph(
                str(data_path / "auth.txt.gz"),
                AUTH_COLUMNS, windows, AUTH_NUMERIC,
                graph, graph.feed_auth_event,
            )
        else:
            n_auth = 0

        if feed_flow:
            n_flow = _stream_gz_to_graph(
                str(data_path / "flows.txt.gz"),
                FLOW_COLUMNS, windows, FLOW_NUMERIC,
                graph, graph.feed_flow_event,
            )
        else:
            n_flow = 0

        g = graph.build()
        build_time = time.perf_counter() - t0
        logger.info(
            f"  Streamed {n_auth:,} auth + {n_flow:,} flow in {build_time:.1f}s"
        )
        logger.info(f"  Graph: {g.vcount():,} nodes, {g.ecount():,} edges")

        # Free the StreamingGraphBuilder (keep only igraph)
        del graph

        # Check red team overlap
        graph_edges = set()
        for e in g.es:
            graph_edges.add((g.vs[e.source]["name"], g.vs[e.target]["name"]))
        rt_in_graph = red_pairs & graph_edges
        logger.info(f"  Red team pairs in graph: {len(rt_in_graph)}/{len(red_pairs)}")

        # Score
        from src.features import extract_all_features
        from src.scorer import score_edges, score_paths, score_graph

        t1 = time.perf_counter()
        all_feat = extract_all_features(g)
        edge_scores = score_edges(g, all_feat["edge_features"])
        paths = score_paths(g, edge_scores)
        graph_result = score_graph(g, all_feat, edge_scores)
        score_time = time.perf_counter() - t1

        # Detection
        threshold = float(np.percentile(edge_scores.values, 95)) if len(edge_scores) > 0 else 0.5
        anomalous_paths = paths[paths["path_score"] > threshold] if len(paths) > 0 else pd.DataFrame()

        detected_pairs: set[tuple[str, str]] = set()
        if len(anomalous_paths) > 0:
            for _, row in anomalous_paths.iterrows():
                nodes = row["path_nodes"]
                for i in range(len(nodes) - 1):
                    pair = (nodes[i], nodes[i + 1])
                    if pair in red_pairs:
                        detected_pairs.add(pair)

        recall = len(detected_pairs) / len(red_pairs) if red_pairs else 0.0
        anomalous_edge_count = int((edge_scores > threshold).sum())
        n_edges = g.ecount()
        red_edge_count = len(rt_in_graph)
        fpr = max(anomalous_edge_count - red_edge_count, 0) / max(n_edges - red_edge_count, 1)
        precision = len(detected_pairs) / max(anomalous_edge_count, 1)
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

        total_events = n_auth + n_flow
        result = {
            "method": method_name,
            "dataset": "LANL-2015",
            "recall": round(recall, 4),
            "fpr": round(fpr, 4),
            "f1": round(f1, 4),
            "auc": 0.0,
            "latency": round(build_time + score_time, 2),
            "throughput": round(total_events / (build_time + score_time), 1),
            "graph_nodes": g.vcount(),
            "graph_edges": g.ecount(),
            "rt_pairs_in_graph": red_edge_count,
            "anomalous_edges": anomalous_edge_count,
            "threshold": round(threshold, 4),
            "max_path_score": round(graph_result["max_path_score"], 4),
            "mean_edge_score": round(graph_result["mean_edge_score"], 4),
        }
        all_results.append(result)
        logger.info(
            f"  {method_name}: recall={recall:.4f}, fpr={fpr:.4f}, f1={f1:.4f}"
        )

        # Free graph memory
        del g

    # DAPT baselines
    logger.info("Running DAPT2020 baselines")
    try:
        from src.baselines.dapt_baselines import run_dapt_baselines
        dapt_results = run_dapt_baselines(data_dir=dapt_dir)
        for r in dapt_results:
            all_results.append({
                "method": r["method_name"],
                "dataset": "DAPT2020",
                "recall": round(r["recall"], 4),
                "fpr": round(r["fpr"], 4),
                "f1": round(r["f1"], 4),
                "auc": round(r["auc"], 4),
                "latency": 0.0,
                "throughput": 0.0,
            })
            logger.info(f"  {r['method_name']}: auc={r['auc']:.4f}, f1={r['f1']:.4f}")
    except Exception as e:
        logger.warning(f"DAPT baselines failed: {e}")

    return all_results


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
    )

    parser = argparse.ArgumentParser(description="Streaming experiment runner")
    parser.add_argument("--data-dir", default="data/LANL-Dataset-2015")
    parser.add_argument("--window-size", type=int, default=3600)
    parser.add_argument("--dapt-dir", default="data/DAPT2020")
    args = parser.parse_args()

    t0 = time.perf_counter()
    results = run_streaming_experiment(
        data_dir=args.data_dir,
        window_seconds=args.window_size,
        dapt_dir=args.dapt_dir,
    )
    elapsed = time.perf_counter() - t0

    # Save
    import os
    os.makedirs("results", exist_ok=True)
    pd.DataFrame(results).to_csv("results/metrics.csv", index=False)
    with open("results/experiment_results.json", "w") as f:
        json.dump(results, f, indent=2)

    # Print summary
    print(f"\n{'='*80}")
    print("EXPERIMENT RESULTS SUMMARY")
    print(f"{'='*80}")
    df = pd.DataFrame(results)
    for _, row in df.iterrows():
        print(f"  {row['method']:20s} | recall={row['recall']:.4f} | fpr={row['fpr']:.4f} | f1={row['f1']:.4f} | auc={row['auc']:.4f}")
    print(f"{'='*80}")
    print(f"Total time: {elapsed:.1f}s")
    print("Results saved to results/metrics.csv and results/experiment_results.json")
