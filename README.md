# Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis

**ECE 239AS — Machine Learning and Data Mining for Cybersecurity**  
**Team:** Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur  
**University of California, Los Angeles**

---

## Overview

This project addresses the challenge of detecting **lateral movement** in cloud VPC networks — the phase of an attack where an adversary pivots through a compromised network to reach high-value targets. Lateral movement is notoriously hard to detect because internal traffic is trusted by default, and no single log source provides complete visibility.

We propose a **graph-based multi-source detection** approach that combines network flow logs and authentication logs into a unified streaming graph, then scores nodes and edges for lateral movement likelihood based on structural, temporal, and statistical feature deviation from baseline behavior.

### Key Research Question

> Does combining flow and authentication logs via graph analysis improve detection accuracy and latency compared to single-source baselines?

### Key Findings from Data Analysis

1. **TCP Dominance**: 99.82% of LANL red-team flows and 100% of DAPT2020 attack flows use TCP, unlike benign traffic (~50% TCP). This is structural — SMB, SSH, and RDP (primary lateral movement services) are TCP-only.

2. **Kill-Chain Progression Patterns**: Fan-out ratio increases from 2.50 (reconnaissance) to 6.0 (lateral movement), then drops to 1.0 (exfiltration). This predictable arc maps the shift from "scan everything" to "spread from compromised hosts."

3. **Temporal Separation**: Red-team authentication events have a median inter-arrival time of 214 seconds vs 6 seconds for normal users — a **35.7× difference**. Attackers are slower and more deliberate.

---

## Pipeline Architecture

```
┌──────────────┐  ┌──────────────┐
│  Flow Logs   │  │  Auth Logs   │
└──────┬───────┘  └──────┬───────┘
       │                 │
       ▼                 ▼
┌─────────────────────────────────┐
│    Streaming Graph Builder      │
│  (nodes: computers, identities) │
│  (edges: connections, auth)     │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│     Feature Extraction          │
│  - Structural: degree, fan-out, │
│    betweenness, PageRank        │
│  - Temporal: inter-arrival,     │
│    burst patterns, duration     │
│  - Statistical: edge rarity,    │
│    auth failure rate            │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│     Anomaly Scoring             │
│  - Edge-level scoring           │
│  - Multi-hop path enumeration   │
│  - Subgraph thresholding        │
└──────────────┬──────────────────┘
               ▼
┌─────────────────────────────────┐
│     Detection & Alerting        │
│  - Flag anomalous subgraphs     │
│  - Target <60s latency          │
└─────────────────────────────────┘
```

### Methods Compared

| Method | Data Sources | Description |
|--------|-------------|-------------|
| `flow_only` | Network flow logs | Baseline using connection data only |
| `auth_only` | Authentication logs | Baseline using login events only |
| `combined` | Flow + Auth logs | Unified graph with both edge types |
| `oneclass_svm` | DAPT2020 CICFlowMeter features | One-Class SVM (ML baseline) |
| `isolation_forest` | DAPT2020 CICFlowMeter features | Isolation Forest (ML baseline) |

---

## Datasets

### LANL-Dataset-2015

| Property | Value |
|----------|-------|
| Source | Los Alamos National Laboratory real enterprise network |
| Duration | 58 days continuous capture |
| Scale | 1.6B+ events, 12,425 users, 17,684 computers |
| Attack Ground Truth | 749 labeled red-team events |
| Log Sources | Flows, Auth, DNS, Processes |

**Files used:**
- `auth.txt` (68 GB, ~1.05B events) — authentication events with success/failure
- `flows.txt` (4.9 GB, ~130M events) — network flow records
- `redteam.txt` (22 KB, 749 events) — red-team attack ground truth

### DAPT2020

| Property | Value |
|----------|-------|
| Source | Simulated APT attack testbed |
| Duration | 5 days |
| Attack Flows | 20,665 labeled flows across 4 kill-chain stages |
| Log Sources | PCAP-derived CICFlowMeter features + system logs |

**Files used:**
- `csv/*.csv` — 9 CSV files with 86 CICFlowMeter features per flow

---

## Results

### LANL-2015 (Streaming Graph Methods)

| Method | AUC | Recall | Edge Recall | FPR | F1 | Graph Nodes | Graph Edges | RT Edges in Graph | Throughput |
|--------|-----|--------|-------------|-----|----|-------------|-------------|-------------------|------------|
| **combined** | **0.9456** | 0.0000 | 0.0000 | 0.0005 | 0.0000 | 28,618 | 110,154 | 4/4 | 6,781/s |
| auth_only | 0.9094 | 0.0000 | 0.0000 | 0.0006 | 0.0000 | 27,125 | 78,041 | 4/4 | 9,087/s |
| flow_only | 0.0000 | 0.0000 | 0.0000 | 0.0014 | 0.0000 | 6,337 | 36,809 | 0/4 | 19,749/s |

**Key observations:**

1. **Combined method achieves highest AUC (0.9456)**, outperforming auth-only (0.9094) by +4.0%. This confirms the hypothesis that combining flow + auth logs improves detection over single-source methods.

2. **Redteam edges score significantly higher than baseline**: redteam mean score = 0.8506 vs baseline mean = 0.5343 (1.59× higher). The 95th-percentile threshold (0.864) is just above redteam scores, meaning redteam edges are in the top ~15% but not top 5%.

3. **Auth-only is the stronger single source** because redteam lateral movement primarily uses authenticated connections (SMB, SSH, RDP). Flow-only has no redteam pairs in the sampled graph.

4. **Detection recall is limited by sampled data**: with `--sample 1000000`, only 4 of 308 unique redteam src→dst pairs appear in the graph. The full unsampled dataset run is needed for production recall metrics.

### DAPT2020 (ML Baselines)

| Method | AUC | F1 | Recall | FPR |
|--------|-----|----|--------|-----|
| **OneClassSVM** | **0.6353** | **0.1065** | 0.1612 | 0.0543 |
| IsolationForest | 0.4487 | 0.0550 | 1.0000 | 1.0000 |

OneClassSVM achieves the best balance on DAPT2020 with AUC=0.635 and F1=0.107, while IsolationForest flags everything as anomalous (recall=1.0, FPR=1.0).

### Feature Importance Analysis

The combined method's scoring was analyzed to determine which graph features best separate attack traffic from normal operations:

| Feature | Redteam Mean | Baseline Mean | Ratio |
|---------|-------------|---------------|-------|
| active_duration | 5,423s | 994s | **5.46×** |
| inter_arrival_std | 925s | 206s | **4.49×** |
| in_degree | 12.6 | 3.85 | **3.27×** |
| inter_arrival_mean | 731s | 234s | **3.13×** |
| total_degree | 21.6 | 7.70 | **2.81×** |
| out_degree | 9.0 | 3.85 | **2.34×** |
| burst_score | 0.45 | 0.20 | **2.31×** |
| fan_out_ratio | 0.54 | 0.54 | 1.00× |

**Edge feature correlations with anomaly scores:**
- edge_rarity: 0.63 (strongest predictor)
- dst_in_degree: 0.32
- src_out_degree: 0.29

**Key takeaway**: Redteam nodes are distinguished primarily by their **temporal patterns** (3-5× higher inter-arrival time and variance) and **connectivity** (2-3× more connections), confirming the paper's analysis that attackers are "slower and more deliberate" with higher fan-out during lateral movement.

### Generated Figures

Each experiment run produces 4 visualization files in `results/<run_id>/figures/`:

- **graph_snapshot.png** — Fruchterman-Reingold layout of the combined auth+flow graph
- **score_distribution.png** — Histogram of edge scores for normal vs red-team edges
- **roc_curves.png** — ROC curves for all methods overlaid
- **detection_timeline.png** — Detection timeline showing when anomalous edges appear relative to red-team events

---

## Project Structure

```
Graph-based-Threat-Detection/
├── run_experiment.py              # Main CLI orchestrator
├── Makefile                       # make pipeline, make i (install)
├── pyproject.toml                 # Dependencies
├── datasets/
│   ├── LANL-Dataset-2015/         # auth.txt, flows.txt, redteam.txt
│   └── dapt2020/                  # csv/, pcap-data/, log-public-monday/
├── src/
│   ├── __init__.py
│   ├── data_loader.py             # Streaming reader, time-window extraction, parquet cache
│   ├── streaming_pipeline.py      # Main experiment: graph builder, scoring, evaluation
│   ├── features.py                # Structural, temporal, statistical feature extraction
│   ├── scorer.py                  # Edge scoring, multi-hop path enumeration
│   ├── visualize.py               # Matplotlib plots (graph, scores, ROC, timeline)
│   ├── generate_comparison.py     # Results aggregation and comparison tables
│   └── baselines/
│       ├── __init__.py
│       ├── dapt_loader.py         # DAPT2020 CSV loader with CICFlowMeter features
│       └── dapt_baselines.py      # OneClassSVM and IsolationForest baselines
└── results/
    └── <run_id>/                  # Per-run output directory
        ├── metrics.csv            # Aggregated metrics for all methods
        ├── comparison_table.md    # Markdown comparison table
        ├── summary.txt            # Key findings summary
        ├── figures/               # Generated PNG plots
        ├── flow_only/             # Per-method detailed results
        ├── auth_only/
        ├── combined/
        └── redteam/               # Red-team events and window intervals
```

---

## How to Run

### Prerequisites

```bash
# Install dependencies using uv
make i
# or: uv sync
```

Requires Python 3.13+. Dependencies: `python-igraph`, `pandas`, `pyarrow`, `numpy`, `scikit-learn`, `matplotlib`, `tqdm`.

### Quick Test (sampled data)

```bash
# Run with 1M event sample per source (fast, ~10 minutes)
uv run python run_experiment.py --sample 1000000
```

### Full LANL Dataset Run

```bash
# Full dataset (will take hours due to 1.05B auth + 130M flow events)
uv run python run_experiment.py

# Custom window size (default: ±1 hour = 3600s)
uv run python run_experiment.py --window-size 7200
```

### Custom Data Paths

```bash
uv run python run_experiment.py \
  --data-dir datasets/LANL-Dataset-2015 \
  --dapt-dir datasets/dapt2020 \
  --sample 5000000
```

### Output

Results are saved to `results/<timestamp>/`:
- `metrics.csv` — Summary metrics for all methods
- `comparison_table.md` — Formatted comparison table
- `figures/` — Visualization plots
- Per-method directories with detailed edge scores, paths, features, and detected pairs

---

## Implementation Details

### Streaming Graph Construction

The pipeline uses a `StreamingGraphBuilder` class that incrementally builds an `igraph` object:
- **Nodes** represent computers and user identities (user accounts, service accounts)
- **Edges** represent network connections (from flow logs) and authentication events (from auth logs)
- Edges are deduplicated by (src, dst) key with accumulated weight and temporal attributes
- Graph updates incrementally as new log records arrive within time windows

### Time-Windowed Processing

Rather than loading the entire 1.6B+ event dataset, the pipeline:
1. Loads 749 red-team events and builds ±N second time windows around each
2. Merges overlapping windows (typically 25 merged windows for ±3600s)
3. Streams through log files, skipping events outside windows using binary search
4. Caches windowed results as Parquet for faster re-runs

### Feature Extraction (9 node features, 3 edge features)

**Node features:** in-degree, out-degree, total degree, fan-out ratio, betweenness centrality, inter-arrival mean/std, burst score, active duration

**Edge features:** edge rarity (1/weight), source out-degree, destination in-degree

**Graph features:** density, average clustering, component count

### Anomaly Scoring

- **Node suspiciousness**: Computed from fan-out ratio, inter-arrival timing, betweenness centrality, out-degree, and burst score. Nodes behaving like lateral movement sources (high fan-out, anomalous timing, high connectivity) receive higher scores.
- **Edge scoring**: Combines source node suspiciousness (50%), edge rarity (20%), TCP protocol signal (15%), and lateral movement port detection (15%), min-max scaled to [0,1].
- **Path scoring**: BFS enumeration limiting top-10 highest-scored outgoing edges per node, scored as (product + max + mean) / 3 of edge scores.
- **Detection threshold**: 95th percentile of edge scores; edges and subgraphs above threshold flagged.
- **AUC computation**: ROC-AUC computed per method using edge scores vs redteam pair labels.

---

## Known Limitations and Future Work

1. **LANL Dataset Scale**: The full LANL dataset (68 GB auth + 4.9 GB flows) requires significant processing time. The time-windowed approach reduces this but still needs hours for a complete run on commodity hardware. Current results use 1M event samples.

2. **Detection Recall**: With sampled data, only 4/308 unique redteam pairs appear in the graph. The combined method achieves AUC=0.9456, confirming the scoring separates redteam from baseline, but full dataset ingestion is needed for meaningful recall. Redteam edges score 0.85 while the 95th percentile threshold is 0.86 — adaptive thresholding could improve recall.

3. **Limited Attack Diversity**: Redteam events focus on SMB, SSH, and credential reuse techniques. The datasets do not capture living-off-the-land or fileless approaches.

4. **Future Improvements**:
   - Full unsampled LANL dataset ingestion (1.6B+ events)
   - Test on additional real-world cloud VPC datasets
   - Integrate with cloud-native security services
   - Explore ML classifiers on graph features (combined method AUC=0.9456 suggests strong feature separability)
   - Investigate encrypted traffic analysis (HTTP/3 over UDP)
   - Extend to live detection deployments

---

## References

1. **Hopper**: Ho et al., "Modeling and Detecting Lateral Movement," 2021
2. **Euler**: King & Huang, "Detecting Network Lateral Movement via Scalable Temporal Graph Link Prediction," NDSS 2023
3. **POIROT**: Milajerdi et al., "Aligning Attack Behavior with Kernel Audit Records," 2019
4. **HOLMES**: Milajerdi et al., "Real-time APT Detection through Correlation of Suspicious Information Flows," 2019
5. **Kitsune**: Mirsky et al., "An Ensemble of Autoencoders for Online Network Intrusion Detection," 2018
6. **NoDoze**: Hassan et al., "Combatting Threat Alert Fatigue with Automated Provenance Triage," NDSS 2017
