# Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis

**ECE 239AS — Machine Learning and Data Mining for Cybersecurity**
**Team:** Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur
**University of California, Los Angeles**

## Quick Start

```bash
make i           # Install dependencies (uv sync)
make pipeline    # Run the detection pipeline
make eval        # Run evaluation analyses (holdout, ablation, sweep)
make check lint  # Lint the codebase
```

Three entry points:

- `main.py` — runs the full pipeline (graph construction → feature extraction → weight optimization → scoring → detection → visualization)
- `feature.py` — runs held-out AUC feature audit on cached pipeline outputs to rank features by discriminative power
- `eval.py` — runs evaluation analyses (holdout optimization, tabular/graph ablation, graph feature sweep) on cached pipeline outputs

## Overview

This project detects **lateral movement** in cloud VPC networks by combining network flow and authentication logs into a unified graph. Edges are scored for anomaly likelihood using a weighted sum of graph features, where weights are automatically optimized via Nelder-Mead to maximize ROC AUC.

**Research Question:** Does combining flow and authentication logs via graph analysis improve detection accuracy compared to single-source baselines?

## Methods

| Method             | Description                        |
| ------------------ | ---------------------------------- |
| `flow_only`        | Network flow logs only             |
| `auth_only`        | Authentication logs only           |
| `combined`         | Unified graph with both edge types |
| `oneclass_svm`     | One-Class SVM on graph features    |
| `isolation_forest` | Isolation Forest on graph features |

## Datasets

- **LANL-2015**: 58 days, 1.6B+ events, 749 red-team events

Download from [LANL CIF Partition](https://csr.lanl.gov/data/cyber1/) and place the three required files (see file structure below).

## Project Structure

```
Graph-Based-Lateral-Movement-Detection/
├── main.py                          # Full pipeline entry point
├── feature.py                       # Feature audit entry point
├── eval.py                          # Evaluation analyses entry point
├── Makefile                         # Build commands
├── pyproject.toml                   # Dependencies (managed by uv)
├── pipeline_config.json             # Pipeline configuration
│
├── data/                            # ⚠️  NOT tracked by git — must provide locally
│   └── LANL-Dataset-2015/           # Required dataset directory
│       ├── auth.txt.gz              #   Authentication events
│       ├── flows.txt.gz             #   Network flow events
│       └── redteam.txt.gz           #   Red-team ground truth
│
├── src/                             # Source code
│   ├── __init__.py
│   ├── config.py                    #   Pipeline config loader
│   ├── types.py                     #   Frozen dataclasses (PipelineConfig, etc.)
│   ├── pipeline.py                  #   Pipeline orchestrator (run, variant workers)
│   ├── stages.py                    #   Stage functions (load, build, score, detect)
│   ├── variants.py                  #   Variant descriptors (combined, auth_only, flow_only)
│   ├── detection.py                 #   Threshold optimization + pair metrics
│   ├── reporting.py                 #   Comparison table generation
│   ├── io.py                        #   Persist results, redteam data, config
│   ├── utils.py                     #   Shared helpers
│   │
│   ├── data/
│   │   ├── __init__.py
│   │   └── lanl.py                  #   Streaming gz reader, window extraction
│   │
│   ├── graph/
│   │   ├── __init__.py
│   │   └── builder.py               #   StreamingGraphBuilder + stream_gz_to_graph
│   │
│   ├── features/
│   │   ├── __init__.py
│   │   ├── edge.py                  #   Edge feature extraction
│   │   └── node.py                  #   Node feature extraction
│   │
│   ├── scoring/
│   │   ├── __init__.py
│   │   ├── edges.py                 #   Edge scoring + path boost
│   │   └── paths.py                 #   Path enumeration + scoring
│   │
│   ├── optimization/
│   │   ├── __init__.py
│   │   └── optimizer.py             #   Nelder-Mead weight optimization
│   │
│   ├── visualization/
│   │   ├── __init__.py
│   │   ├── comparison.py            #   Method comparison plots
│   │   ├── roc.py                   #   ROC curve plots
│   │   ├── scores.py                #   Score distribution plots
│   │   ├── snapshot.py              #   Graph snapshot visualization
│   │   ├── style.py                 #   Shared plot styling
│   │   └── timeline.py              #   Timeline plots
│   │
│   ├── eval/
│   │   ├── __init__.py
│   │   ├── holdout_optimizer.py     #   Held-out weight optimization eval
│   │   ├── tabular_graph_ablation.py#   Tabular vs graph feature ablation
│   │   └── graph_feature_sweep.py   #   Graph feature sweep eval
│   │
│   └── feature_audit/
│       ├── __init__.py
│       ├── loader.py                #   Load cached pipeline outputs
│       ├── joiner.py                #   Join features with labels
│       ├── scorer.py                #   Per-feature AUC scoring
│       ├── reporter.py              #   Markdown report generation
│       └── types.py                 #   AuditConfig dataclass
│
├── report/                          # LaTeX report and draft sections
├── results/                         # Pipeline outputs (auto-generated, gitignored)
├── feature_results/                 # Feature audit outputs (auto-generated, gitignored)
└── analysis_results/                # Evaluation outputs (auto-generated, gitignored)
```

### Required Data Files

The pipeline expects these files relative to the repo root (configured in `pipeline_config.json`):

```
data/LANL-Dataset-2015/
├── auth.txt.gz        # Authentication events (required)
├── flows.txt.gz       # Network flow events (required)
└── redteam.txt.gz     # Red-team ground truth (required)
```

To set up the dataset:

1. Download from [LANL CIF Partition](https://csr.lanl.gov/data/cyber1/)
2. Create `data/LANL-Dataset-2015/` in the repo root
3. Place `auth.txt.gz`, `flows.txt.gz`, and `redteam.txt.gz` inside

If your dataset lives elsewhere, edit `pipeline_config.json`:

```json
{
  "data": {
    "lanl_dir": "data/LANL-Dataset-2015"
  }
}
```

All paths in the config are relative to the repo root. No absolute paths are used anywhere in the codebase.

## Configuration

All pipeline parameters live in `pipeline_config.json`. Every path is relative to the project root — the repo can be cloned anywhere and will work as long as the dataset files are in place.

### `data` — Dataset paths

| Option        | Default                    | Description                                                       |
| ------------- | -------------------------- | ----------------------------------------------------------------- |
| `lanl_dir`    | `"data/LANL-Dataset-2015"` | Path to LANL dataset directory (relative to repo root)            |
| `window_size` | `3600`                     | Time window (seconds) around each red-team event for scoping data |

### `graph` — Graph construction

| Option           | Default  | Description                                  |
| ---------------- | -------- | -------------------------------------------- |
| `progress_every` | `500000` | Log progress every N events during streaming |

### `scoring` — Scoring and thresholding

| Option                   | Default                        | Description                                                                                               |
| ------------------------ | ------------------------------ | --------------------------------------------------------------------------------------------------------- |
| `threshold_mode`         | `"auto_optimize"`              | `"auto_optimize"` sweeps percentiles to maximize F1; any other value uses `threshold_percentile` directly |
| `threshold_percentile`   | `99`                           | Percentile for threshold when not in auto_optimize mode                                                   |
| `threshold_search_range` | `[90, 95, 97, 99, 99.5, 99.9]` | Percentiles to sweep in auto_optimize mode                                                                |
| `path_boost_factor`      | `0.1`                          | Boost added to edges appearing in top-scoring paths                                                       |
| `temporal_decay_rate`    | `0.0`                          | Exponential decay rate for temporal weighting (disabled when 0)                                           |
| `max_hops`               | `4`                            | Maximum path length for path enumeration                                                                  |
| `top_k_paths`            | `50`                           | Number of top-scoring paths to retain                                                                     |
| `top_outgoing_per_node`  | `10`                           | Top outgoing edges per node to follow during path search                                                  |

### `features` — Feature extraction

| Option                      | Default | Description                                                                         |
| --------------------------- | ------- | ----------------------------------------------------------------------------------- |
| `betweenness_node_limit`    | `5000`  | Node count threshold for switching from exact to approximate betweenness centrality |
| `approximate_betweenness`   | `true`  | Use igraph cutoff parameter for approximate betweenness                             |
| `betweenness_cutoff`        | `3`     | Cutoff parameter for approximate betweenness                                        |
| `temporal_burst_window_pct` | `0.1`   | Fraction of node active span for burst score computation                            |
| `max_workers`               | `20`    | Parallel workers for feature extraction and path scoring                            |

## Output

Results saved to `results/<run_id>/`:

- `metrics.csv` — Summary metrics per method
- `pipeline_run.json` — Full pipeline metadata and timing
- `figures/` — Visualization plots (graph snapshot, ROC curves, score distribution, timeline)
- `optimization/` — Weight optimization logs and optimized weights
- `comparison_table.md` — Method comparison
- `LANL-2015/<variant>/` — Per-variant outputs (edge_scores.csv, paths.csv, features, etc.)
- `redteam/` — Red-team events and window intervals

Feature audit outputs saved to `feature_results/<audit_id>/`:

- `feature_audit_results.json` — Per-feature AUC and statistics
- `Feature_Audit_Results.md` — Human-readable markdown report
- `metadata.json` — Audit run metadata

Evaluation outputs saved to `analysis_results/<run_id>/`:

- `optimization_holdout/` — held-out weight optimization results
- `tabular_vs_graph_ablation/` — feature group ablation results
- `graph_features_test/` — graph feature sweep results
