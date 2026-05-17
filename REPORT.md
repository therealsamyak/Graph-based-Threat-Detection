# Graph-Based Lateral Movement Detection — Project Report

## 1. Methodology

### 1.1 Dataset
The pipeline uses the **LANL Unified Host and Network Dataset (2015)**, which contains real enterprise network telemetry including:
- **Authentication events** (Windows auth logs with user, computer, auth type, logon type)
- **Network flow events** (source/destination computers, ports, protocol, packet/byte counts)
- **Red team activity** (ground truth labels for adversarial lateral movement)

### 1.2 Graph Construction
Network events are streamed incrementally to build a **directed, weighted graph** where:
- **Nodes** represent computers and users in the network
- **Edges** represent authentication or flow relationships, with attributes including event type, timing, and frequency
- A **time-windowed approach** (±1 hour around red team events) filters the dataset to relevant activity periods

### 1.3 Scoring Pipeline
The detection pipeline applies a multi-stage scoring process:

1. **Edge Scoring** — Each edge is scored using a weighted combination of features:
   - `is_ntlm`: Whether the authentication uses the legacy NTLM protocol
   - `source_fan_out`: Number of unique destinations from the source
   - `dst_in_degree`: Number of incoming connections to the destination
   - `is_network_logon`: Whether the logon is a network-based authentication
   - `dst_fan_out_ratio`: Ratio of destination's outgoing to total connections

2. **Weight Optimization** — The Nelder-Mead algorithm optimizes edge feature weights to maximize AUC on a held-out calibration set, improving from a baseline AUC of ~0.198 (equal weights) to ~0.968.

3. **Path Enumeration** — The top-scoring edges are used to enumerate lateral movement paths (up to 4 hops), identifying multi-hop attack chains.

4. **Path Boosting** — Edge scores are boosted based on their participation in high-scoring paths, amplifying signals for edges that form part of attack chains.

5. **Threshold Optimization** — An auto-optimization search finds the best percentile threshold to balance recall and false positive rate.

### 1.4 Feature Audit
A comprehensive feature audit evaluates **26+ features** using held-out AUC to rank individual feature discriminative power. Features are tested for duplicates, variance, and mean separation between red team and benign traffic.

### 1.5 Evaluation Suite
Three evaluation analyses are performed:
- **Holdout Optimization**: Compares the custom weight optimizer against logistic regression on a 50/50 train/test split
- **Tabular vs Graph Ablation**: Measures the contribution of graph-derived features vs. pure tabular (non-graph) features
- **Graph Feature Sweep**: Tests incremental AUC gains from adding graph topology features (PageRank, Personalized PageRank, k-core, community detection, similarity metrics)

---

## 2. Results

### 2.1 Detection Performance
| Metric | Value |
|--------|-------|
| **AUC** | 0.9685 |
| **Recall** | 84.42% |
| **False Positive Rate** | 2.09% |
| **F1 Score** | 0.0461 |
| **Threshold** | 0.8467 (97th percentile) |
| **Red team pairs in graph** | 305 |
| **Detected pairs** | 260 |
| **Anomalous edges flagged** | 10,960 |

The pipeline achieves **high recall (84.4%)** with a **low false positive rate (2.1%)**, demonstrating effective detection of lateral movement activity.

### 2.2 Weight Optimization
| Metric | Equal Weights | Optimized |
|--------|--------------|-----------|
| AUC | 0.1979 | **0.9685** |
| Improvement | — | **+389%** |

Optimized weights:
| Feature | Weight |
|---------|--------|
| `is_ntlm` | 0.295 |
| `is_network_logon` | 0.258 |
| `dst_fan_out_ratio` | 0.237 |
| `source_fan_out` | 0.215 |
| `dst_in_degree` | ~0.000 |

NTLM authentication and network logon events are the strongest individual signals, while `dst_in_degree` receives near-zero weight.

### 2.3 Feature Audit — Top Features by AUC
| Feature | AUC | Δ Mean (Red Team − Benign) |
|---------|-----|---------------------------|
| `is_ntlm` | 0.9327 | +0.865 |
| `source_fan_out` | 0.9060 | +0.279 |
| `dst_in_degree` | 0.8189 | −3.764 |
| `dst_fan_out_ratio` | 0.8178 | +0.310 |
| `is_network_logon` | 0.8170 | +0.634 |
| `dst_total_degree` | 0.8122 | −3.203 |
| `edge_rarity` | 0.8085 | +0.401 |

### 2.4 Holdout Evaluation
| Method | Calibration AUC | Eval AUC | Overfit Gap |
|--------|----------------|----------|-------------|
| Weight Optimizer | 0.9689 | 0.9681 | 0.0008 |
| Logistic Regression | 0.9738 | 0.9733 | 0.0005 |

Both methods generalize well with minimal overfitting (< 0.1% gap). Logistic regression slightly outperforms the custom optimizer.

### 2.5 Tabular vs Graph Ablation
| Feature Set | # Features | Eval AUC |
|-------------|-----------|----------|
| Pure Tabular Only | 9 | 0.9562 |
| Graph-Derived Only | 17 | 0.9891 |
| Combined | 26 | **0.9922** |

- Adding graph features to tabular: **+3.6% AUC gain**
- Adding tabular features to graph: **+0.3% AUC gain**
- **Graph-derived features are the primary driver of detection performance.**

### 2.6 Graph Feature Sweep
| Feature Group | Added Features | Eval AUC | Δ vs Base |
|---------------|---------------|----------|-----------|
| Base (5 features) | — | 0.9733 | — |
| + PageRank | 2 | 0.9734 | +0.0002 |
| + **Personalized PageRank** | 2 | **0.9956** | **+0.0224** |
| + k-core | 2 | 0.9771 | +0.0039 |
| + Community | 3 | 0.9781 | +0.0048 |
| + Similarity (Jaccard/Adamic-Adar) | 2 | 0.9733 | +0.0001 |
| **All Combined** | 11 | **0.9948** | **+0.0215** |

**Personalized PageRank** (targeted toward the attacker host `C17693`) is the single most impactful graph feature, providing a +2.2% AUC improvement on its own.

---

## 3. Takeaways

### 3.1 Key Findings
1. **Graph-based detection significantly outperforms tabular-only approaches.** Graph-derived features alone achieve 0.989 AUC vs. 0.956 for pure tabular features.
2. **Personalized PageRank is the highest-value graph feature.** Targeting random walks toward known attacker hosts dramatically improves detection accuracy.
3. **NTLM authentication is the strongest single indicator.** Legacy authentication protocols are heavily exploited in lateral movement and should be prioritized for monitoring and remediation.
4. **Weight optimization matters.** Equal-weight scoring achieves only 0.198 AUC; optimized weights push this to 0.968+.
5. **The pipeline generalizes well.** Overfitting gaps are under 0.1% across all evaluation methods.

### 3.2 Operational Recommendations
- **Monitor NTLM usage**: Flag all NTLM authentication events, especially from unusual source hosts
- **Track fan-out patterns**: Hosts with abnormally high outbound connection counts are strong lateral movement indicators
- **Deploy Personalized PageRank**: Use attacker-host-targeted PageRank as a real-time scoring feature
- **Combine graph + tabular features**: The full 26-feature set achieves the best overall performance (0.992 AUC)

### 3.3 Limitations
- The F1 score (0.046) is low due to the extreme class imbalance — the high threshold (97th percentile) prioritizes precision over recall, resulting in many false positives relative to true positives
- Path enumeration is computationally expensive (~9 minutes for 122M paths on this dataset)
- Results are specific to the LANL 2015 dataset; performance on other environments may vary

### 3.4 Pipeline Structure
```
main.py → results/<run_id>/<dataset>/combined/
feature.py → feature_results/<audit_id>/
eval.py → analysis_results/<eval_id>/
```

---

*Report generated from run `20260516_090835` (main pipeline), `20260516_222714` (feature audit), and `20260516_222717` (evaluation suite).*
