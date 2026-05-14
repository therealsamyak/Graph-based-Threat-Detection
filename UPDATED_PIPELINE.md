# UPDATED PIPELINE — Branch `feat/gradient-descent-draft` vs `main`

## Verification Summary

| Check | Status | Notes |
|-------|--------|-------|
| Combined-only pipeline | ✅ PASS | `run_method_pipeline` hardcodes `method_name = "combined"`, always feeds both auth+flow |
| No hardcoded weights | ✅ PASS | Weights are optimized at runtime via `WeightOptimizer` (Nelder-Mead), fallback to equal weights |
| LANL2015 only | ✅ PASS | All DAPT2020 references removed. No dataset selection logic. Only LANL data loaded |
| No weird CLI args | ✅ PASS | Only `--sample` remains. `--data-dir`, `--window-size`, `--dapt-dir` all removed |
| No weird config options | ✅ PASS | `pipeline_config.json` has clean scoring/features sections only. No `flow_weights`, `auth_weight_multiplier`, `BaselinesConfig` |
| Feature module | ✅ PASS | Edge (16 features), node (9 features), graph (5 features) — all fully implemented, no stubs |
| All code implemented | ✅ PASS | No `TODO`, `NotImplementedError`, empty `pass`, or unimplemented stubs found |
| **Runs properly** | ❌ FAIL | **Two bugs block execution** (see below) |

### Bugs Found

#### Bug 1: Data path mismatch (BLOCKS EXECUTION)

`main.py` line 61 and `pipeline_config.json` both reference `datasets/LANL-Dataset-2015`, but the actual directory is `data/LANL-Dataset-2015`. The pipeline fails immediately:

```
FileNotFoundError: [Errno 2] No such file or directory: 'datasets/LANL-Dataset-2015/redteam.txt.gz'
```

**Fix**: Change `main.py` line 61 from `"datasets/LANL-Dataset-2015"` to `"data/LANL-Dataset-2015"`, and update `pipeline_config.json` `data.lanl_dir` to match.

#### Bug 2: reporting.py crashes on empty CSV

If the LANL experiment fails (e.g. due to Bug 1), `results/pending/metrics.csv` is empty. `generate_comparison()` calls `pd.read_csv()` on it, which throws `pandas.errors.EmptyDataError`. This is an unguarded crash path.

**Fix**: Guard `generate_comparison` against empty/missing CSV, or skip reporting when `results_df` is empty.

---

## Full Pipeline Flow

When you run `main.py`, here's the complete execution path:

### 1. Entry: `main.py::run()`

```
main.py::main()
  └─ main.py::run(argv=None)
       ├─ _parse_args()          # Only --sample N (limit events for testing)
       ├─ load_config()          # Loads pipeline_config.json → PipelineConfig
       │
       │  # Hardcoded: data_dir="datasets/LANL-Dataset-2015", window_seconds=3600
       │
       └─ src.pipeline.run_streaming_experiment(data_dir, window_seconds, max_events, config)
```

### 2. Pipeline Orchestrator: `src/pipeline.py::run_streaming_experiment()`

```
src/pipeline.py::run_streaming_experiment()
  ├─ Generate run_id (timestamp), create results/{run_id}/ directory
  ├─ save_pipeline_config()                    # Persist config to results dir
  │
  ├─ stages.load_redteam_data(data_dir, window_seconds)
  │    ├─ load_redteam("redteam.txt.gz")       # Parse red team events
  │    ├─ Build red_pairs = set of (src_comp, dst_comp) tuples
  │    ├─ build_window_intervals(rt, window)   # Merge red team events into time windows
  │    └─ save_redteam_data()                  # Persist to results dir
  │
  ├─ stages.run_method_pipeline()              # ← CORE (see below)
  │
  ├─ io.save_method_results()                  # Save edge_scores.csv, paths.csv, features, etc.
  │
  ├─ Build ExperimentResult dataclass
  │
  ├─ Save pipeline_run.json (full metadata)
  │
  └─ Return (results_list, experiment_result_dict, results_dir_path)
```

### 3. Core Pipeline: `src/stages.py::run_method_pipeline()`

```
stages.run_method_pipeline()
  │
  │  method_name = "combined" (always)
  │
  ├─ STEP 1: STREAM & BUILD GRAPH
  │    ├─ StreamingGraphBuilder()
  │    ├─ stream_gz_to_graph("auth.txt.gz") → graph.feed_auth_event()
  │    ├─ stream_gz_to_graph("flows.txt.gz") → graph.feed_flow_event()
  │    └─ graph.build() → igraph.Graph  (directed, weighted, with time/auth attributes)
  │
  ├─ STEP 2: FEATURE EXTRACTION
  │    └─ features.extract_all_features(g)
  │         ├─ extract_edge_features(g)     # 16 features per edge
  │         ├─ extract_node_features(g)     # 9 features per node
  │         └─ extract_graph_features(g)    # 5 graph-level metrics
  │
  ├─ STEP 3: WEIGHT OPTIMIZATION
  │    ├─ WeightOptimizer(edge_features, labels, feature_names)
  │    ├─ optimizer.optimize()  (Nelder-Mead, maximizes AUC)
  │    │    ├─ Initial weights: equal (0.2 each)
  │    │    ├─ Objective: minimize(-AUC)
  │    │    ├─ Callbacks log each iteration
  │    │    └─ Returns optimized weights dict
  │    └─ Fallback: equal weights if optimization fails
  │
  ├─ STEP 4: EDGE SCORING
  │    ├─ scoring.score_edges(g, edge_features, weights=optimized_weights)
  │    │    ├─ Weighted sum of 5 features (is_ntlm, source_fan_out, dst_in_degree,
  │    │    │   is_network_logon, dst_fan_out_ratio)
  │    │    ├─ Rank-transform edge_rarity, protocol_rarity
  │    │    ├─ Zero out self-loops and user edges ("@" in name)
  │    │    └─ Returns pd.Series of scores [0,1]
  │    │
  │    └─ scoring.score_paths(g, edge_scores, max_hops, top_k, top_outgoing)
  │         ├─ BFS path enumeration from each node
  │         ├─ Parallel via ProcessPoolExecutor
  │         ├─ Score paths: (geo_mean + max + mean) / 3 of edge scores
  │         └─ Return top-50 anomalous paths
  │
  ├─ STEP 5: PATH BOOST
  │    └─ scoring.boost_edges_from_paths(edge_scores, paths, boost_factor=0.1)
  │         └─ Edges in high-score paths get boosted: score += 0.1 * path_score
  │
  ├─ STEP 6: GRAPH-LEVEL SCORING
  │    └─ scoring.score_graph(g, all_features, edge_scores, paths)
  │         └─ Returns: max/mean path score, anomalous path count, max/mean edge score
  │
  ├─ STEP 7: THRESHOLD OPTIMIZATION
  │    ├─ Build DetectionParams (scores, masks, red team pairs, graph edges)
  │    └─ detection.optimize_threshold(params, mode="auto_optimize")
  │         ├─ Sweep percentiles [90, 95, 97, 99, 99.5, 99.9]
  │         ├─ For each: compute F1 at that percentile threshold
  │         └─ Return threshold with best F1
  │
  ├─ STEP 8: METRICS COMPUTATION
  │    └─ detection.compute_pair_metrics(params, threshold)
  │         ├─ Anomalous pairs = edges above threshold (valid only)
  │         ├─ Detected = anomalous ∩ red_team_pairs
  │         ├─ recall = |detected| / |all_red_pairs|
  │         ├─ FPR = false_positives / (FP + TN)
  │         ├─ F1, precision
  │         └─ AUC (sklearn.metrics.roc_auc_score on valid edges)
  │
  └─ Return MethodResult (graph, scores, features, metrics, timing)
```

### 4. Back in `main.py::run()` — Output & Visualization

```
main.py::run() (continued)
  ├─ Save metrics.csv, experiment_results.json, per_method_details.json
  ├─ generate_comparison(results_dir)        # Markdown comparison report
  │
  ├─ Visualization (all saved to results/figures/)
  │    ├─ plot_graph_snapshot()               # Network graph visualization
  │    ├─ plot_score_distribution()           # Score histogram with red team overlay
  │    ├─ plot_detection_timeline()           # Scores over time with red team events
  │    ├─ plot_roc_curves()                   # ROC curves
  │    └─ plot_method_comparison()            # Bar chart of method metrics
  │
  └─ _print_summary()                        # Console table of metrics
```

---

## Diff vs `main` Branch

### Summary: 18 files changed, +599 / -941 lines

### What was REMOVED

| Item | Details |
|------|---------|
| `--data-dir`, `--window-size`, `--dapt-dir` CLI args | `main.py` no longer accepts these. Path and window are hardcoded. |
| `src/baselines/` entire directory | All baseline runners deleted: `lanl_baselines.py`, `dapt_baselines.py`, `dapt_graph.py`, `extra_baselines.py`, `shared_baselines.py` |
| DAPT2020 support | `DataConfig.dapt_dir`, `_mp_run_dapt_baselines()`, all DAPT loading code removed |
| `method_name` parameter | `run_method_pipeline()` no longer takes method name — always `"combined"` |
| `feed_auth` / `feed_flow` toggles | Always feeds both auth and flow data |
| Separate LANL baselines | `_mp_run_lanl_baselines()`, parallel baseline execution removed |
| `FlowWeights` dataclass | Separate flow edge scoring weights removed |
| `auth_weight_multiplier` config | Auth edge boost multiplier removed |
| `BaselinesConfig` dataclass | OneClass SVM, Isolation Forest, DAPT graph config all removed |
| Hardcoded scoring weights | `ScoringWeights(is_ntlm=0.4, is_network_logon=0.3, edge_rarity=0.3)` no longer used as defaults for edge scoring |
| `src/utils.py` functions | 53 lines of utility functions removed |
| `src/reporting.py` complexity | Reduced from comparison of multiple methods to simpler output |

### What was ADDED

| Item | Details |
|------|---------|
| `src/optimization/optimizer.py` | `WeightOptimizer` class — Nelder-Mead optimization of feature weights, maximizes AUC. 297 lines. Logs each iteration, saves optimization report JSON. |
| `src/optimization/__init__.py` | Module exports |
| Weight optimization in `stages.py` | Before scoring, runs `WeightOptimizer` on valid edge features against red team labels. Falls back to equal weights on failure. |
| `optimize_weights.py` (root) | Standalone weight optimization script (41 lines) |
| Unified edge scoring | `score_edges()` now uses a single weighted sum of 5 features (no separate auth/flow scoring paths) |
| Scoring summary logging | `score_edges()` logs weight distribution, per-feature contributions, percentile stats |
| `pipeline_run.json` output | Complete run metadata including timing, feature stats, intermediate values |
| `features/edge.py` additions | 5 lines of new feature extraction support |

### What was CHANGED

| Before (main) | After (this branch) |
|----------------|---------------------|
| 3 methods: `flow_only`, `auth_only`, `combined` | 1 method: `combined` only |
| Hardcoded weights: `{is_ntlm: 0.4, is_network_logon: 0.3, edge_rarity: 0.3}` | Optimized weights via Nelder-Mead, fallback equal weights |
| Separate auth/flow scoring paths in `score_edges()` | Unified weighted sum across all edge types |
| `ScoringConfig` had `weights`, `flow_weights`, `auth_weight_multiplier` | `ScoringConfig` has only `weights` (used for defaults, overridden by optimizer) |
| Multi-method comparison in reporting | Single combined result output |
| `pipeline_config.json` had DAPT config, flow_weights, baselines config | Clean config with only scoring + features sections |

### Files Deleted (present in main, gone here)

- `src/baselines/__init__.py`
- `src/baselines/dapt_baselines.py`
- `src/baselines/dapt_graph.py`
- `src/baselines/extra_baselines.py`
- `src/baselines/lanl_baselines.py`
- `src/baselines/shared_baselines.py`

### Files Added (new in this branch)

- `src/optimization/__init__.py`
- `src/optimization/optimizer.py`
- `optimize_weights.py`

---

## Architecture Diagram

```
main.py
  │
  ├── config.py (load_config → PipelineConfig)
  │
  └── pipeline.py (run_streaming_experiment)
        │
        ├── stages.py
        │     ├── load_redteam_data()
        │     │     └── data/lanl.py (load_redteam, build_window_intervals)
        │     │
        │     └── run_method_pipeline()  ← CORE
        │           ├── graph/builder.py (StreamingGraphBuilder, stream_gz_to_graph)
        │           ├── features/__init__.py (extract_all_features)
        │           │     ├── features/edge.py  → 16 edge features
        │           │     ├── features/node.py  → 9 node features
        │           │     └── graph-level metrics
        │           │
        │           ├── optimization/optimizer.py (WeightOptimizer → Nelder-Mead)
        │           ├── scoring/edges.py (score_edges, boost_edges_from_paths)
        │           ├── scoring/paths.py (score_paths, score_graph)
        │           └── detection.py (optimize_threshold, compute_pair_metrics)
        │
        ├── io.py (save_method_results, save_pipeline_config, save_redteam_data)
        │
        └── [back in main.py]
              ├── reporting.py (generate_comparison)
              └── visualization/ (5 plot functions)
```

---

## Config File: `pipeline_config.json` (current branch)

```json
{
  "data": {
    "lanl_dir": "datasets/LANL-Dataset-2015",
    "window_size": 3600
  },
  "graph": {
    "progress_every": 500000
  },
  "scoring": {
    "threshold_mode": "auto_optimize",
    "threshold_percentile": 99,
    "threshold_search_range": [90, 95, 97, 99, 99.5, 99.9],
    "path_boost_factor": 0.1,
    "temporal_decay_rate": 0.0,
    "max_hops": 4,
    "top_k_paths": 50,
    "top_outgoing_per_node": 10
  },
  "features": {
    "betweenness_node_limit": 5000,
    "approximate_betweenness": true,
    "betweenness_cutoff": 3,
    "temporal_burst_window_pct": 0.1,
    "max_workers": 12
  }
}
```

Note: `weights` section removed from config — weights are now optimized at runtime.

## CLI Arguments

Only one argument:

```
--sample N    Limit number of events per source (for quick testing)
```

No `--data-dir`, `--window-size`, `--dapt-dir`, `--method`, or other options.
