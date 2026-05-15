# Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis

**ECE 239AS — Machine Learning and Data Mining for Cybersecurity**  
**Team:** Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur  
**University of California, Los Angeles**

## Quick Start

```bash
make i           # Install dependencies (uv sync)
make pipeline    # Run the detection pipeline
make check lint  # Lint the codebase
```

## Overview

This project detects **lateral movement** in cloud VPC networks by combining network flow and authentication logs into a unified graph. We score nodes and edges for anomaly likelihood using structural, temporal, and statistical features.

**Research Question:** Does combining flow and authentication logs via graph analysis improve detection accuracy compared to single-source baselines?

## Methods

| Method | Description |
|--------|-------------|
| `flow_only` | Network flow logs only |
| `auth_only` | Authentication logs only |
| `combined` | Unified graph with both edge types |
| `combined` | Graph-based detection on DAPT2020 flow graph |
| `oneclass_svm` | One-Class SVM on graph features |
| `isolation_forest` | Isolation Forest on graph features |

## Datasets

- **LANL-2015**: 58 days, 1.6B+ events, 749 red-team events (auth.txt.gz, flows.txt.gz, redteam.txt.gz)
- **LANL-2017**: Additional LANL dataset
- **DAPT2020**: 5-day simulated APT, 20,665 labeled flows (CSV files with CICFlowMeter features)

## Results

### LANL-2015

| Method | AUC | Recall | F1 |
|--------|-----|--------|-----|
| combined | 0.0000 | 0.0000 | 0.0000 |
| auth_only | 0.0000 | 0.0000 | 0.0000 |
| flow_only | 0.0000 | 0.0000 | 0.0000 |

*Note: Detection recall limited by sampled data. Full dataset run needed for meaningful metrics.*

### DAPT2020

| Method | AUC | F1 | Recall |
|--------|-----|----|--------|
| OneClassSVM | **0.5534** | 0.1065 | 0.1612 |
| IsolationForest | 0.4785 | 0.0051 | 0.0069 |

## Project Structure

```
Graph-Based-Lateral-Movement-Detection/
├── main.py              # CLI orchestrator
├── Makefile             # Build commands
├── pyproject.toml       # Dependencies
├── pipeline_config.json  # Pipeline configuration
├── data/                # Dataset files (.gz)
├── src/                 # Source code (data, graph, features, scoring, visualization, baselines)
├── report/              # LaTeX report and project description
└── results/             # Experiment outputs and figures
```

## Configuration

Edit `pipeline_config.json` to adjust scoring weights, threshold mode, and feature extraction parameters.

## Output

Results saved to `results/<run_id>/`:
- `metrics.csv` — Summary metrics
- `figures/` — Visualization plots (graph snapshot, ROC curves, timelines)
- `comparison_table.md` — Method comparison
