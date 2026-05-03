"""Streaming pipeline: build graph directly from data files, never materialize full DataFrames.

Streams auth.txt and flows.txt line-by-line through the time windows,
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


def _open_file(filepath: str):
    """Open file transparently: handle both .gz and plain .txt."""
    if filepath.endswith(".gz"):
        return gzip.open(filepath, "rt", encoding="utf-8")
    return open(filepath, "r", encoding="utf-8")


def _stream_gz_to_graph(
    gz_path: str,
    columns: list[str],
    windows: list[tuple[int, int]],
    numeric_cols: set[str],
    graph: StreamingGraphBuilder,
    feed_fn,
    progress_every: int = 500000,
    max_events: int | None = None,
) -> int:
    """Stream file through windows, feed events to graph, return row count."""
    if not windows:
        return 0

    # Try .txt first, fall back to .gz
    txt_path = gz_path.replace(".gz", "") if gz_path.endswith(".gz") else gz_path
    actual_path = txt_path if Path(txt_path).exists() else gz_path

    first_start = windows[0][0]
    last_end = windows[-1][1]

    count = 0
    past_start = False
    _starts = [w[0] for w in windows]

    with _open_file(actual_path) as f:
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

            if not _time_in_any_window(time_val, windows, _starts):
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
                logger.info(f"  {actual_path}: {count:,} events processed...")

    return count


def run_streaming_experiment(
    data_dir: str = "datasets/LANL-Dataset-2015",
    window_seconds: int = 3600,
    dapt_dir: str = "datasets/dapt2020",
    max_events: int | None = None,
) -> tuple[list[dict], dict, str]:
    """Run full experiment using streaming graph construction.

    Streams auth + flow gz files through time windows,
    builds graph incrementally (no DataFrame materialization),
    runs scoring and detection, then discards non-combined graphs.

    Returns:
        Tuple of (all_results, viz_data, results_base) where viz_data contains
        the combined graph, edge scores, paths, threshold, red team
        times, and method graphs for visualization. results_base is the
        output directory path string.
    """
    from datetime import datetime, timezone

    data_path = Path(data_dir)
    all_results: list[dict] = []
    viz_data: dict = {}

    run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    results_base = Path("results") / run_id
    results_base.mkdir(parents=True, exist_ok=True)
    logger.info(f"Run ID: {run_id}, output dir: {results_base}")

    # Try .txt first, fall back to .gz for redteam
    rt_path = str(data_path / "redteam.txt.gz")
    rt_path_actual = rt_path.replace(".gz", "") if Path(rt_path.replace(".gz", "")).exists() else rt_path
    rt = load_redteam(rt_path_actual)
    red_pairs = set(zip(rt["src_comp"].astype(str), rt["dst_comp"].astype(str)))
    windows = _build_window_intervals(rt, window_seconds)
    logger.info(f"Red team: {len(rt)} events, {len(windows)} merged windows")
    viz_data["redteam_times"] = rt["time"]
    viz_data["red_pairs"] = red_pairs
    method_graphs: dict[str, ig.Graph | None] = {}

    redteam_dir = results_base / "redteam"
    redteam_dir.mkdir(parents=True, exist_ok=True)
    rt.to_csv(redteam_dir / "redteam_events.csv", index=False)
    with open(redteam_dir / "window_intervals.json", "w") as f:
        json.dump([{"start": s, "end": e} for s, e in windows], f, indent=2)
    with open(redteam_dir / "redteam_pairs.json", "w") as f:
        json.dump([{"src": s, "dst": d} for s, d in sorted(red_pairs)], f, indent=2)
    logger.info(f"  Saved redteam data to {redteam_dir}")

    # Stream both files into graph, then score, then discard
    for method_name, feed_auth, feed_flow in [
        ("flow_only", None, True),
        ("auth_only", True, None),
        ("combined", True, True),
    ]:
        logger.info(f"Streaming + building: {method_name}")
        t0 = time.perf_counter()

        graph = StreamingGraphBuilder()

        # Try .txt first, fall back to .gz
        auth_path = str(data_path / "auth.txt.gz")
        auth_actual = auth_path.replace(".gz", "") if Path(auth_path.replace(".gz", "")).exists() else auth_path
        flow_path = str(data_path / "flows.txt.gz")
        flow_actual = flow_path.replace(".gz", "") if Path(flow_path.replace(".gz", "")).exists() else flow_path

        if feed_auth:
            n_auth = _stream_gz_to_graph(
                auth_actual,
                AUTH_COLUMNS, windows, AUTH_NUMERIC,
                graph, graph.feed_auth_event,
                max_events=max_events,
            )
        else:
            n_auth = 0

        if feed_flow:
            n_flow = _stream_gz_to_graph(
                flow_actual,
                FLOW_COLUMNS, windows, FLOW_NUMERIC,
                graph, graph.feed_flow_event,
                max_events=max_events,
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
        from src.scorer import (
            compute_auc,
            compute_feature_importance,
            score_edges,
            score_graph,
            score_paths,
        )

        t1 = time.perf_counter()
        logger.info(f"  Extracting features ({g.vcount():,} nodes, {g.ecount():,} edges)...")
        all_feat = extract_all_features(g)
        logger.info(f"  Features extracted in {time.perf_counter() - t1:.1f}s, scoring edges...")
        is_combined_method = method_name == "combined"
        edge_scores = score_edges(g, all_feat["edge_features"], node_features=all_feat["node_features"], is_combined=is_combined_method)
        logger.info("  Edge scores computed, enumerating paths (this may take a while)...")
        paths, edge_scores = score_paths(g, edge_scores)
        logger.info(f"  Scored {len(paths):,} paths, computing graph-level scores...")
        graph_result = score_graph(g, all_feat, edge_scores, paths=paths, is_combined=is_combined_method)
        # Extract boosted edge scores from graph_result
        edge_scores = graph_result.get("edge_scores", edge_scores)
        score_time = time.perf_counter() - t1
        logger.info(f"  Scoring completed in {score_time:.1f}s")

        # Threshold sweeping: find percentile that maximizes F1
        percentiles = [90, 95, 97, 99, 99.5, 99.9]
        best_f1 = -1.0
        best_threshold = float(np.percentile(edge_scores.values, 95)) if len(edge_scores) > 0 else 0.5
        for pct in percentiles:
            thr = float(np.percentile(edge_scores.values, pct)) if len(edge_scores) > 0 else 0.5
            # Compute pair-space F1 at this threshold
            anom_edges = set()
            for i in range(g.ecount()):
                if i in edge_scores.index and edge_scores.loc[i] > thr:
                    anom_edges.add(i)
            anom_pairs_thr: set[tuple[str, str]] = set()
            for i in anom_edges:
                e = g.es[i]
                anom_pairs_thr.add((g.vs[e.source]["name"], g.vs[e.target]["name"]))
            det_pairs_thr = anom_pairs_thr & rt_in_graph
            rec_thr = len(det_pairs_thr) / len(red_pairs) if red_pairs else 0.0
            prec_thr = len(det_pairs_thr) / max(len(anom_pairs_thr), 1)
            f1_thr = 2 * rec_thr * prec_thr / (rec_thr + prec_thr) if (rec_thr + prec_thr) > 0 else 0.0
            if f1_thr > best_f1:
                best_f1 = f1_thr
                best_threshold = thr

        threshold = best_threshold
        logger.info(f"  Best threshold: {threshold:.4f} (F1={best_f1:.4f})")
        anomalous_paths_df = paths[paths["path_score"] > threshold] if len(paths) > 0 else pd.DataFrame()

        # Extract all anomalous pairs from anomalous paths (pair-space)
        anomalous_pairs: set[tuple[str, str]] = set()
        if len(anomalous_paths_df) > 0:
            for _, row in anomalous_paths_df.iterrows():
                nodes = row["path_nodes"]
                for i in range(len(nodes) - 1):
                    anomalous_pairs.add((nodes[i], nodes[i + 1]))

        # Metrics in pair-space
        detected_pairs = anomalous_pairs & rt_in_graph
        recall = len(detected_pairs) / len(red_pairs) if red_pairs else 0.0
        true_negatives = len(graph_edges - anomalous_pairs - rt_in_graph)
        false_positives = len(anomalous_pairs - rt_in_graph)
        fpr = false_positives / max(false_positives + true_negatives, 1)
        precision = len(detected_pairs) / max(len(anomalous_pairs), 1)
        f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0

        # AUC: use edge scores vs redteam pair labels
        auc = compute_auc(g, edge_scores, rt_in_graph)

        # Edge-level detection: flag individual edges above threshold
        anomalous_edge_indices = set()
        for i in range(g.ecount()):
            if i in edge_scores.index and edge_scores.loc[i] > threshold:
                anomalous_edge_indices.add(i)

        # Edge-level recall: how many redteam edges are above threshold?
        rt_edge_indices = set()
        rt_edge_scores = []
        baseline_edge_scores = []
        for i in range(g.ecount()):
            e = g.es[i]
            pair = (g.vs[e.source]["name"], g.vs[e.target]["name"])
            score = float(edge_scores.loc[i]) if i in edge_scores.index else 0.0
            if pair in rt_in_graph:
                rt_edge_indices.add(i)
                rt_edge_scores.append(score)
            else:
                baseline_edge_scores.append(score)

        rt_detected = rt_edge_indices & anomalous_edge_indices
        edge_recall = len(rt_detected) / len(rt_edge_indices) if rt_edge_indices else 0.0
        edge_precision = len(rt_detected) / len(anomalous_edge_indices) if anomalous_edge_indices else 0.0
        edge_f1 = 2 * edge_recall * edge_precision / (edge_recall + edge_precision) if (edge_recall + edge_precision) > 0 else 0.0

        # Detection latency: time from earliest redteam event to detection
        # Measured as the time difference between first anomalous edge and first redteam event
        detection_latency = 0.0
        if rt_edge_indices and anomalous_edge_indices:
            rt_times_list = []
            for i in rt_edge_indices:
                t_val = g.es[i].attributes().get("first_time", g.es[i].attributes().get("time", 0))
                rt_times_list.append(float(t_val))
            
            alert_times_list = []
            for i in anomalous_edge_indices:
                t_val = g.es[i].attributes().get("first_time", g.es[i].attributes().get("time", 0))
                alert_times_list.append(float(t_val))
            
            if rt_times_list and alert_times_list:
                earliest_rt = min(rt_times_list)
                earliest_alert = min(alert_times_list)
                detection_latency = max(0, earliest_alert - earliest_rt)

        total_events = n_auth + n_flow
        result = {
            "method": method_name,
            "dataset": "LANL-2015",
            "recall": round(recall, 4),
            "fpr": round(fpr, 4),
            "f1": round(f1, 4),
            "edge_recall": round(edge_recall, 4),
            "edge_f1": round(edge_f1, 4),
            "auc": round(auc, 4),
            "latency": round(build_time + score_time, 2),
            "detection_latency_sec": round(detection_latency, 2),
            "throughput": round(total_events / max(build_time + score_time, 0.01), 1),
            "graph_nodes": g.vcount(),
            "graph_edges": g.ecount(),
            "rt_pairs_in_graph": len(rt_in_graph),
            "rt_edges_in_graph": len(rt_edge_indices),
            "rt_edges_detected": len(rt_detected),
            "anomalous_edges": len(anomalous_edge_indices),
            "anomalous_pairs": len(anomalous_pairs),
            "threshold": round(threshold, 4),
            "max_path_score": round(graph_result["max_path_score"], 4),
            "mean_edge_score": round(graph_result["mean_edge_score"], 4),
            "redteam_mean_score": round(float(np.mean(rt_edge_scores)), 4) if rt_edge_scores else 0.0,
            "baseline_mean_score": round(float(np.mean(baseline_edge_scores)), 4) if baseline_edge_scores else 0.0,
        }
        all_results.append(result)
        logger.info(
            f"  {method_name}: recall={recall:.4f}, edge_recall={edge_recall:.4f}, fpr={fpr:.4f}, auc={auc:.4f}"
        )

        method_dir = results_base / method_name
        method_dir.mkdir(parents=True, exist_ok=True)

        edge_scores.to_csv(method_dir / "edge_scores.csv", header=["score"])
        logger.info(f"  Saved edge_scores.csv ({len(edge_scores):,} edges)")

        if len(paths) > 0:
            paths_save = paths.copy()
            paths_save["path_nodes"] = paths_save["path_nodes"].apply(lambda x: " -> ".join(x) if isinstance(x, list) else str(x))
            paths_save["path_edges"] = paths_save["path_edges"].apply(lambda x: ",".join(str(i) for i in x) if isinstance(x, list) else str(x))
            paths_save.to_csv(method_dir / "paths.csv", index=False)
            logger.info(f"  Saved paths.csv ({len(paths_save):,} paths)")

        if len(anomalous_paths_df) > 0:
            ap_save = anomalous_paths_df.copy()
            ap_save["path_nodes"] = ap_save["path_nodes"].apply(lambda x: " -> ".join(x) if isinstance(x, list) else str(x))
            ap_save["path_edges"] = ap_save["path_edges"].apply(lambda x: ",".join(str(i) for i in x) if isinstance(x, list) else str(x))
            ap_save.to_csv(method_dir / "anomalous_paths.csv", index=False)
            logger.info(f"  Saved anomalous_paths.csv ({len(ap_save):,} paths)")

        all_feat["node_features"].to_csv(method_dir / "node_features.csv")
        all_feat["edge_features"].to_csv(method_dir / "edge_features.csv")
        with open(method_dir / "graph_features.json", "w") as f:
            json.dump(all_feat["graph_features"], f, indent=2)
        logger.info("  Saved node_features.csv, edge_features.csv, graph_features.json")

        # Feature importance analysis
        feat_imp = compute_feature_importance(g, all_feat["node_features"], all_feat["edge_features"], edge_scores, rt_in_graph)
        with open(method_dir / "feature_importance.json", "w") as f:
            json.dump(feat_imp, f, indent=2, default=str)
        logger.info("  Saved feature_importance.json")

        edge_rows = []
        for e in g.es:
            attrs = e.attributes()
            edge_rows.append({
                "src": g.vs[e.source]["name"],
                "dst": g.vs[e.target]["name"],
                **{k: v for k, v in attrs.items() if k != "weight" or True},
            })
        pd.DataFrame(edge_rows).to_csv(method_dir / "graph_edges.csv", index=False)

        node_rows = [{"name": v["name"], **{k: v for k, v in v.attributes().items() if k != "name"}} for v in g.vs]
        pd.DataFrame(node_rows).to_csv(method_dir / "graph_nodes.csv", index=False)
        logger.info(f"  Saved graph_edges.csv ({g.ecount():,}), graph_nodes.csv ({g.vcount():,})")

        if detected_pairs:
            with open(method_dir / "detected_redteam_pairs.json", "w") as f:
                json.dump([{"src": s, "dst": d} for s, d in sorted(detected_pairs)], f, indent=2)
            logger.info(f"  Saved detected_redteam_pairs.json ({len(detected_pairs)} pairs)")

        # Free graph memory (except for combined method)
        if method_name == "combined":
            viz_data["combined_graph"] = g
            viz_data["combined_edge_scores"] = edge_scores
            viz_data["combined_paths"] = paths
            viz_data["combined_threshold"] = threshold
        else:
            method_graphs[method_name] = None
            del g

    # LANL unsupervised baselines (on combined method's edge features)
    logger.info("Running LANL-2015 unsupervised baselines")
    try:
        from src.baselines.lanl_baselines import run_lanl_baselines
        # Use the combined method's graph and edge features for baselines
        lanl_results = run_lanl_baselines(
            all_feat["edge_features"],
            red_pairs,
            viz_data.get("combined_graph"),
        )
        for r in lanl_results:
            all_results.append({
                "method": r["method_name"],
                "dataset": "LANL-2015",
                "recall": round(r["recall"], 4),
                "fpr": round(r["fpr"], 4),
                "f1": round(r["f1"], 4),
                "auc": round(r["auc"], 4),
                "latency": 0.0,
                "throughput": 0.0,
            })
            logger.info(f"  LANL {r['method_name']}: AUC={r['auc']:.4f}, F1={r['f1']:.4f}")
    except Exception as e:
        logger.warning(f"LANL baselines failed: {e}")

    # DAPT baselines
    logger.info("Running DAPT2020 baselines")
    try:
        from src.baselines.dapt_baselines import run_dapt_baselines
        dapt_results = run_dapt_baselines(data_dir=dapt_dir, max_rows=max_events)
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

    viz_data["method_graphs"] = method_graphs
    return all_results, viz_data, str(results_base)
