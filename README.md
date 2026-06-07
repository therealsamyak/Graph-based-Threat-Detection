# Graph-Based Lateral Movement Detection

**ECE 239AS: Machine Learning and Data Mining for Cybersecurity**
**Team:** Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur
**University of California, Los Angeles**

## Overview

This project detects **lateral movement** in network logs by combining network flow and authentication logs into a unified graph. Each edge gets an anomaly score from a weighted sum of graph features; weights are tuned automatically via Nelder-Mead to maximize ROC AUC.

**Research question:** Can combining flow and auth logs through graph analysis beat single-source baselines at detecting lateral movement?

## Methods

| Method             | Description                        |
| ------------------ | ---------------------------------- |
| `flow_only`        | Network flow logs only             |
| `auth_only`        | Authentication logs only           |
| `combined`         | Unified graph with both edge types |
| `oneclass_svm`     | One-Class SVM on graph features    |
| `isolation_forest` | Isolation Forest on graph features |

## Prerequisites

- **Python 3.13** (pinned in `.python-version`)
- **[uv](https://docs.astral.sh/uv/)** package manager

Install uv if you don't have it:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Dependencies are declared in `pyproject.toml` and locked in `uv.lock`. No `requirements.txt`.

## Quick Start

Three commands from clone to figures:

```bash
uv sync                  # Install dependencies into .venv
make results             # Run full pipeline (feature → main → baselines → eval)
for s in scripts/fig*.py scripts/tbl*.py; do uv run "$s"; done
                         # Generate all figures/tables into figures/
```

## Data Setup

Raw datasets are **not tracked by git**. The `data/` directory is gitignored. See [`data/README_DATA.md`](data/README_DATA.md) for raw download instructions.

The local `data/` directory currently contains:

```
data/
├── LANL-Dataset-2015/     # auth.txt.gz, flows.txt.gz, redteam.txt.gz
├── LANL-Dataset-2017/
└── dapt2020/
```

The pipeline reads LANL-2015 by default. If your dataset lives elsewhere, edit `pipeline_config.json`:

```json
{
  "data": { "lanl_dir": "data/LANL-Dataset-2015" }
}
```

All paths in the config are relative to the repo root; no absolute paths.

### Required Files

```
data/LANL-Dataset-2015/
├── auth.txt.gz        # Authentication events (required)
├── flows.txt.gz       # Network flow events (required)
└── redteam.txt.gz     # Red-team ground truth (required)
```

## Pipeline

`make results` runs the full detection pipeline in order:

| Stage                       | Command              | Output directory         |
| --------------------------- | -------------------- | ------------------------ |
| Feature audit               | `uv run feature.py`  | `feature_results/`       |
| Detection pipeline          | `uv run main.py`     | `results/`               |
| Baselines (SVM, IF)         | `uv run baselines.py`| `baseline_results/`      |
| Evaluation analyses         | `uv run eval.py`     | `analysis_results/`      |

All four output directories are gitignored. They are regenerated on every run.

Entry points:

- `main.py`: graph construction, feature extraction, weight optimization, scoring, detection, visualization
- `feature.py`: held-out AUC feature audit on cached pipeline outputs
- `eval.py`: holdout optimization, tabular/graph ablation, graph feature sweep
- `baselines.py`: One-Class SVM and Isolation Forest baselines

## Figure and Table Reproduction

Every figure and table is reproduced by a standalone script in `scripts/`. Run from the repo root:

```bash
uv run scripts/fig_roc.py                 # single figure
uv run scripts/fig_roc.py --run-id 20260525_050958   # pin to a specific run
```

Run all of them at once:

```bash
for s in scripts/fig*.py scripts/tbl*.py; do uv run "$s"; done
```

### Run Contract

- **Invocation:** `uv run scripts/figN_<name>.py [--run-id ID]` from the repo root
- **`--run-id`**: the only optional argument. Default is auto-discover latest run. Use it to pin to a specific `results/<run-id>/` directory.
- **Output:** always written to `figures/`
- **Failure mode:** scripts exit 1 with a clear message if results data is missing (e.g. "Run 'make results' first")

## Script Manifest

16 scripts, each producing one or more outputs in `figures/`:

| Script | Output(s) |
| ------ | --------- |
| `scripts/fig_roc.py` | `roc_curves_{combined,auth_only,flow_only}.png` |
| `scripts/fig_scores.py` | `score_distribution.png` |
| `scripts/fig_method_comparison.py` | `method_comparison_{auc,f1,recall}.png` |
| `scripts/fig_radar_chart.py` | `radar_chart_{combined,auth_only,flow_only}.png` |
| `scripts/fig_variant_heatmap.py` | `variant_heatmap_{auc,f1,recall}.png` |
| `scripts/fig_detection_counts.py` | `detection_counts.png` |
| `scripts/fig_performance_tradeoff.py` | `performance_tradeoff.png` |
| `scripts/fig_metrics_summary.py` | `metrics_summary.png` |
| `scripts/fig_score_distributions.py` | `score_distributions_{combined,auth_only,flow_only}.png` |
| `scripts/fig_detection_timeline.py` | `detection_timeline_{combined,auth_only,flow_only}.png` |
| `scripts/fig_graph_statistics.py` | `graph_statistics.png` |
| `scripts/fig_holdout_validation.py` | `holdout_validation.png` |
| `scripts/fig_feature_audit.py` | `feature_audit_{combined,auth_only,flow_only}.png` |
| `scripts/fig_ablation.py` | `ablation_study.png` |
| `scripts/fig_feature_sweep.py` | `feature_sweep_{combined,auth_only,flow_only}.png` |
| `scripts/tbl1_methods_comparison.py` | `methods_comparison.md` |

## Makefile Targets

| Target            | Command                | What it does                                          |
| ----------------- | ---------------------- | ----------------------------------------------------- |
| `make i`          | `uv sync`              | Install dependencies                                  |
| `make feature`    | `uv run feature.py`    | Feature audit only                                    |
| `make pipeline`   | `uv run main.py`       | Detection pipeline only                               |
| `make baselines`  | `uv run baselines.py`  | Baselines only                                        |
| `make eval`       | `uv run eval.py`       | Evaluation analyses only                              |
| `make figures`    | `uv run figures.py`    | Legacy combined figure runner                         |
| `make results`    | feature → pipeline → baselines → eval | Full pipeline, regenerates all results |
| `make all`        | full run + commit + push | Regenerate everything and publish                   |
| `make test`       | sample runs + cleanup  | Smoke test on 10-sample subsets                       |
| `make check`      | `uvx ruff check --fix .` | Lint                                                 |

## Project Structure

```
Graph-Based-Lateral-Movement-Detection/
├── main.py                          # Pipeline entry point
├── feature.py                       # Feature audit entry point
├── eval.py                          # Evaluation analyses entry point
├── baselines.py                     # Baselines entry point
├── Makefile                         # Build commands
├── pyproject.toml                   # Dependencies (managed by uv)
├── uv.lock                          # Locked dependency versions
├── pipeline_config.json             # Pipeline configuration
│
├── data/                            # NOT tracked (gitignored)
│   ├── LANL-Dataset-2015/
│   ├── LANL-Dataset-2017/
│   └── dapt2020/
│
├── src/                             # Source code
│   ├── config.py                    #   Pipeline config loader
│   ├── types.py                     #   Frozen dataclasses
│   ├── pipeline.py                  #   Pipeline orchestrator
│   ├── stages.py                    #   Stage functions
│   ├── variants.py                  #   Variant descriptors
│   ├── detection.py                 #   Threshold optimization
│   ├── reporting.py                 #   Comparison tables
│   ├── io.py                        #   Persist results
│   ├── utils.py                     #   Shared helpers
│   ├── data/lanl.py                 #   Streaming gz reader
│   ├── graph/builder.py             #   StreamingGraphBuilder
│   ├── features/{edge,node}.py      #   Feature extraction
│   ├── scoring/{edges,paths}.py     #   Edge scoring, path boost
│   ├── optimization/optimizer.py    #   Nelder-Mead optimization
│   ├── visualization/               #   Plot helpers
│   ├── eval/                        #   Holdout, ablation, sweep
│   └── feature_audit/               #   AUC feature audit
│
├── scripts/                         # Reproducible figure/table scripts (16)
│   ├── _common.py                   #   Shared CLI + data guards
│   ├── fig_*.py                     #   Figure generators
│   └── tbl*.py                      #   Table generators
│
├── figures/                         # Generated figures and tables
├── results/                         # Pipeline outputs (gitignored)
├── feature_results/                 # Feature audit outputs (gitignored)
├── analysis_results/                # Evaluation outputs (gitignored)
├── baseline_results/                # Baseline outputs (gitignored)
├── report/                          # LaTeX report
└── tests/                           # Tests
```

## Results Provenance

All results directories are gitignored. The grader regenerates everything from source:

1. `uv sync` to install the pinned environment
2. `make results` to run the pipeline and write `results/`, `feature_results/`, `analysis_results/`, `baseline_results/`
3. `uv run scripts/fig*.py` and `uv run scripts/tbl*.py` to write figures and tables into `figures/`

To pin a figure to a specific run rather than auto-discovering the latest:

```bash
uv run scripts/fig_roc.py --run-id 20260525_050958
```

## Configuration

All pipeline parameters live in `pipeline_config.json`. Every path is relative to the project root.

### `data`: Dataset paths

| Option        | Default                    | Description                                                       |
| ------------- | -------------------------- | ----------------------------------------------------------------- |
| `lanl_dir`    | `"data/LANL-Dataset-2015"` | Path to LANL dataset directory (relative to repo root)            |
| `window_size` | `3600`                     | Time window (seconds) around each red-team event for scoping data |

### `graph`: Graph construction

| Option           | Default  | Description                                  |
| ---------------- | -------- | -------------------------------------------- |
| `progress_every` | `500000` | Log progress every N events during streaming |

### `scoring`: Scoring and thresholding

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

### `features`: Feature extraction

| Option                      | Default | Description                                                                         |
| --------------------------- | ------- | ----------------------------------------------------------------------------------- |
| `betweenness_node_limit`    | `5000`  | Node count threshold for switching from exact to approximate betweenness centrality |
| `approximate_betweenness`   | `true`  | Use igraph cutoff parameter for approximate betweenness                             |
| `betweenness_cutoff`        | `3`     | Cutoff parameter for approximate betweenness                                        |
| `temporal_burst_window_pct` | `0.1`   | Fraction of node active span for burst score computation                            |
| `max_workers`               | `20`    | Parallel workers for feature extraction and path scoring                            |

## Output

Pipeline outputs land in `results/<run_id>/`:

- `metrics.csv`: summary metrics per method
- `pipeline_run.json`: full pipeline metadata and timing
- `figures/`: inline visualizations
- `optimization/`: weight optimization logs and optimized weights
- `comparison_table.md`: method comparison
- `LANL-2015/<variant>/`: per-variant edge scores, paths, features
- `redteam/`: red-team events and window intervals

Feature audit outputs in `feature_results/<timestamp>/`:

- `<variant>/feature_audit_results.json`: per-feature AUC and statistics
- `<variant>/Feature_Audit_Results.md`: markdown report
- `summary.json`: combined top features across variants

Evaluation outputs in `analysis_results/<run_id>/`:

- `optimization_holdout/`: held-out weight optimization
- `tabular_vs_graph_ablation/`: feature group ablation
- `graph_features_test/`: graph feature sweep
