# Methodology, Data, and Experimental Setup

## Research Question

This project investigates whether graph-based analysis of network authentication and flow data can effectively detect lateral movement in enterprise networks. Specifically, we ask: can constructing directed graphs from host-to-host authentication events and network flow records, and then scoring edges based on structural and behavioral features, identify the same source-destination pairs that appear in red team attack logs with higher accuracy than conventional anomaly detection methods?

## Data Sources

Our experiments draw on two distinct datasets, each providing a different lens on the lateral movement detection problem.

### LANL Cybersecurity Dataset (LANL-2015)

The primary dataset is the Los Alamos National Laboratory's comprehensive cybersecurity dataset from 2015, which contains 1.6 billion authentication events, 348 million network flow records, and 749 documented red team events spread across 308 unique source-destination host pairs. The data is organized into three gzipped CSV files: `auth.txt.gz` records authentication events with fields including timestamp, source and destination users and computers, authentication type, logon type, authentication orientation, and success/failure status; `flows.txt.gz` records network flow events with timestamp, duration, source and destination computers and ports, protocol, packet count, and byte count; and `redteam.txt.gz` provides the ground-truth red team activity with timestamps, user, and source/destination computers.

We apply a time-windowing strategy to scope the data to relevant periods. For each of the 749 red team events, we define a window spanning +/- 3600 seconds around the event timestamp. Overlapping windows are merged, producing 25 non-overlapping intervals. Only events falling within these windows are included in the experiment. Because the red team events span a large portion of the dataset's time range, these merged windows capture approximately 104 million authentication events and 31.6 million flow events.

### DAPT2020 Dataset

The secondary dataset is the Detecting and Preventing Cyber Attacks (DAPT2020) dataset, which provides pre-extracted CICFlowMeter features from network traffic captures. This dataset contains 86,690 flow records with 77 numerical features including packet length statistics, inter-arrival times, flag counts, and segment size averages, along with activity and stage labels. Lateral movement samples are identified by filtering the `Stage` column for entries containing "lateral movement." This dataset serves as a benchmark for comparing our graph-based approach against classical unsupervised anomaly detection methods that operate on tabular features rather than graph structure.

## Graph Construction

We model the network as a directed multigraph using the igraph library, where nodes represent entities (computers and users) and edges represent interactions between them (authentication events and network flows). The graph is constructed incrementally via a streaming approach: raw gzipped CSV files are read line-by-line, each event is validated against the time windows, and qualifying events are fed directly into the graph without materializing intermediate DataFrames in memory. This design allows the pipeline to process over 135 million events within approximately 4 gigabytes of RAM.

For authentication events, the system creates two types of edges: a computer-to-computer edge from the source computer to the destination computer, and optionally a user-to-user edge from the source user to the destination user. Each edge stores attributes including authentication type, logon type, orientation, success status, and timestamp. When multiple events share the same source-destination pair, the edge weight is incremented and the first and last timestamps are preserved, producing a deduplicated graph with frequency information.

For network flow events, a single computer-to-computer edge is created for each source-destination pair, storing protocol, source and destination ports, packet count, byte count, duration, and timestamp. As with authentication edges, duplicate source-destination pairs are collapsed into a single edge with incremented weight.

Node types are inferred heuristically: any node name ending with `$` or containing `$` before an `@` symbol is classified as a machine account, while others are classified as users. This distinction is used during scoring to exclude user-to-user edges, which carry no lateral movement signal in our methodology.

Three graph variants are constructed for each experiment run: a flow-only graph containing only network flow edges (approximately 11,586 nodes and 131,562 edges), an auth-only graph containing only authentication edges (approximately 90,783 nodes and 409,100 edges), and a combined graph incorporating both data sources (approximately 91,589 nodes and 512,529 edges). After scoring and evaluation, each graph is freed from memory before constructing the next, keeping peak memory usage bounded.

## Feature Extraction

Once the graph is constructed, we extract structural, behavioral, and temporal features at the node, edge, and graph levels. All features are computed per-method (i.e., independently for each of the three graph variants).

### Node Features

For each node, we compute in-degree, out-degree, total degree, and fan-out ratio (out-degree divided by total degree). Betweenness centrality is computed for graphs with fewer than 5,000 nodes using exact igraph computation; for larger graphs, we use an approximate computation with a path length cutoff of 3 hops, which captures local bridging behavior without the O(n^3) cost of exact computation. Temporal features include mean and standard deviation of inter-arrival times between outgoing edges, a burst score measuring the maximum fraction of outgoing edges that fall within any 10% window of the node's active time span, and total active duration.

### Edge Features

For each edge, we compute edge rarity (the reciprocal of edge weight, measuring how unusual the connection frequency is), source out-degree and destination in-degree (contextualizing the edge within the local graph structure), and binary indicators for authentication-specific signals: whether the authentication uses NTLM (a protocol often associated with lateral movement), whether the logon type is Network (indicating remote access), and whether the authentication was successful. We also flag self-loops (source equals destination) and user edges (both endpoints are user nodes), as these are excluded from anomaly scoring. For flow edges specifically, we compute five additional features: an unusual destination port indicator flagging ports commonly used in lateral movement (SSH-22, Telnet-23, SMB-445, RDP-3389, WinRM-5985/5986) or ephemeral ports above 49152; protocol rarity measured as one minus the ratio of edges using that protocol to total flow edges; byte-per-packet ratio as a percentile rank across all edges; duration z-score across the edge population; and temporal decay weight (currently inactive with rate=0.0).

### Graph Features

At the graph level, we compute density, average clustering coefficient, number of connected components, node count, and edge count. These features provide context for interpreting the structural complexity of each graph variant.

## Anomaly Scoring

### Edge Scoring

Edges are scored using a weighted combination of discriminative features, with the scoring formula differing by edge type. Authentication edges are scored as:

```
score_auth = 0.4 * is_ntlm + 0.3 * is_network_logon + 0.3 * rarity_rank
```

where `rarity_rank` is the percentile rank of the edge's rarity value across all edges. This formula assigns higher scores to edges exhibiting known lateral movement indicators: NTLM authentication (which is uncommon in normal traffic but frequently used in pass-the-hash attacks), network logon type (indicating remote access rather than interactive sessions), and rare connections (low-frequency source-destination pairs).

Flow edges use a separate three-feature formula:

```
score_flow = 0.4 * rarity_rank + 0.3 * is_unusual_dst_port + 0.3 * protocol_rarity_rank
```

This gives flow edges meaningful anomaly signals beyond simple rarity, incorporating the suspiciousness of the destination port and protocol.

For the combined method, authentication edges receive a 1.5x multiplier (`auth_weight_multiplier`), ensuring that the typically more informative authentication signals are not diluted by the larger number of flow edges. Self-loops and user-to-user edges are forced to a score of 0.0 and excluded from all downstream analysis.

### Path Enumeration and Scoring

Beyond individual edges, we enumerate multi-hop paths through the graph to capture chain-like lateral movement patterns. Starting from each node, we perform breadth-first search up to a maximum of 4 hops, exploring only the top 10 outgoing edges per node ranked by edge score (pruning low-scored branches). The path enumeration is parallelized across 12 CPU workers using Python's ProcessPoolExecutor.

Each path is scored as the average of three aggregate measures of its constituent edge scores: geometric mean (emphasizing consistently anomalous paths), maximum edge score (capturing paths with at least one highly anomalous segment), and arithmetic mean. The top 50 paths by score are retained. After path enumeration, edge scores are boosted by adding 10% of any path score that traverses the edge (`path_boost_factor = 0.1`), feeding path-level anomaly information back into edge-level detection.

### Threshold Optimization

Anomalous edges are identified by applying a threshold to the final edge scores. Rather than using a fixed percentile (as in our initial experiments), the current pipeline uses an auto-optimization procedure: it sweeps across percentiles [90, 95, 97, 99, 99.5, 99.9] and selects the threshold that maximizes the F1 score against the known red team pairs. This search is performed in pair-space: after thresholding, the set of anomalous source-destination pairs is compared against the ground-truth red team pairs to compute recall, precision, and F1. The auto-optimizer selected the 95th percentile for auth-only and 97th percentile for flow-only and combined methods in our most recent experiments.

### Evaluation Metrics

We evaluate each method using four metrics computed in pair-space: recall (fraction of red team pairs detected), false positive rate (fraction of non-red-team pairs flagged as anomalous), F1 score (harmonic mean of precision and recall), and area under the ROC curve (AUC). The AUC is computed using sklearn's `roc_auc_score` over all valid edges (excluding self-loops and user edges), with ground-truth labels derived from the red team pair set. This provides a threshold-independent measure of discriminative power.

## Baseline Methods

To contextualize our graph-based approach, we compare against two classical unsupervised anomaly detection methods: One-Class SVM with an RBF kernel (gamma="scale", nu=0.1) and Isolation Forest (100 estimators, contamination=0.05). Both are trained on normal-only samples and evaluated against held-out data containing both normal and lateral movement samples.

In our current implementation, these baselines operate on pre-extracted CICFlowMeter features from the DAPT2020 dataset (77 numerical features including packet statistics, inter-arrival times, flag counts, and flow durations). This provides a reference point for what is achievable with tabular features on a standard network traffic dataset. However, this comparison has a significant methodological limitation: the baselines and graph methods are evaluated on different datasets, making direct comparison invalid. We address this in the planned experiments below.

## Preliminary Results

Our most recent experiment run (Run ID 20260502_165755) produced the following results:

**LANL-2015 (graph-based methods):**

| Method | Recall | FPR | F1 | AUC | Threshold | Percentile |
|---|---|---|---|---|---|---|
| flow_only | 0.013 | 0.030 | 0.002 | 0.579 | 0.691 | 97th |
| auth_only | 0.747 | 0.030 | 0.036 | 0.951 | 1.401 | 95th |
| combined | 0.662 | 0.020 | 0.039 | 0.954 | 1.407 | 97th |

**DAPT2020 (tabular baselines):**

| Method | Recall | FPR | F1 | AUC |
|---|---|---|---|---|
| OneClassSVM | 1.000 | 1.000 | 0.055 | 0.646 |
| IsolationForest | 0.007 | 0.050 | 0.005 | 0.449 |

The combined graph method achieves the highest AUC (0.954) and lowest FPR (1.96%) among LANL methods, while auth-only achieves the highest recall (74.7%). However, we cannot directly compare these results against the DAPT2020 baselines because they operate on different data with different ground truth. The flow-only method achieves an AUC of only 0.579 (barely above random), confirming that authentication data carries the primary detection signal. The OneClassSVM baseline is currently non-functional (flags everything as anomalous), and IsolationForest detects almost nothing — both require threshold fixes described below.

## What Remains to Be Done

While the current results demonstrate that our graph-based methodology has strong discriminative power (AUC > 0.95), significant work remains to harden the methodology and validate it with rigorous experiments. We plan five additional experiments, described below.

### Cross-Dataset Validation and Baseline Alignment

Our most pressing methodological issue is that the graph methods and baselines currently run on different datasets (LANL-2015 vs. DAPT2020), making the comparison meaningless. We plan to fix this in both directions. First, we will extract tabular features from the LANL-2015 graph edges (rarity, degree statistics, authentication flags, temporal burst scores) and run OneClassSVM and IsolationForest on the same ground-truth red team labels that our graph methods are evaluated against. Second, we will construct a directed graph from the DAPT2020 flow records (source IP to destination IP edges with CICFlowMeter features as edge attributes) and apply our graph-based scoring methodology to it, comparing against the tabular baselines on DAPT2020's ground truth. This bidirectional evaluation will produce a fair comparison matrix where every method is evaluated on every dataset, allowing us to determine whether the graph approach's advantage is due to methodology or simply different data.

### Threshold Optimization Under Recall Constraints

The current threshold optimizer maximizes F1 alone, which produced a substantial recall drop (from 95.4% to 74.7% for auth-only) compared to our initial fixed-threshold experiments. In a security context, missing a lateral movement event is typically far more costly than investigating a false alarm. We plan to reformulate the threshold search along two dimensions: optimizing the F2 score (which weights recall twice as much as precision) and enforcing a minimum recall constraint (e.g., 90%) then minimizing FPR subject to that constraint. For each objective function (F1, F2, constrained recall), we will sweep the same percentile range [90, 95, 97, 99, 99.5, 99.9] and report the resulting operating point on the ROC curve. This will reveal the precision-recall tradeoff surface and allow us to select a threshold appropriate for the high-cost-of-missed-detection setting.

### Feature Ablation Study

Our current edge scoring formulas use manually tuned feature weights based on domain knowledge about lateral movement indicators. To validate these choices and identify which features actually drive performance, we will conduct a systematic ablation study. For each method (auth-only and combined), we will run the pipeline with each feature individually removed and measure the impact on F1, recall, and AUC. For auth edges, we will test removing NTLM indicator, network logon indicator, and edge rarity individually. For flow edges, we will test removing unusual port flag and protocol rarity. The results will quantify each feature's marginal contribution and may reveal that some features add noise rather than signal, informing a more principled weight assignment.

### Two-Stage Ensemble Detection

Auth-only achieves higher recall (74.7%) while combined achieves higher AUC (0.954) and lower FPR (1.96%), suggesting complementary strengths. We plan to implement a two-stage ensemble: a first stage using auth-only with a lower threshold (targeting high recall), followed by a second stage that re-scores the flagged pairs using the combined graph's edge scores and graph-level features such as whether the pair appears in a high-scoring path, the betweenness centrality of the intermediate nodes, and the burst score of the source node. This approach could achieve both high recall and low FPR by using the methods sequentially rather than independently.

### Statistical Significance Testing

Current results are from a single experiment run, which makes it impossible to distinguish genuine performance differences from random variation. To establish statistical significance, we will run 5-10 experiment iterations, varying the baseline model random seed and the time window half-width (sampling from {600, 1800, 3600} seconds). For each configuration, we will report mean and standard deviation of F1, recall, FPR, and AUC across all iterations. We will use paired t-tests to determine whether observed differences between methods (e.g., combined vs. auth-only on F1, graph-based vs. baseline on AUC) are statistically significant at the p < 0.05 level.

### Summary of Planned Experiments

| # | Experiment | Variables | Primary Metric |
|---|---|---|---|
| 1 | Cross-dataset + baseline alignment | baselines on LANL, graph on DAPT2020 | AUC, F1 per dataset per method |
| 2 | Threshold optimization | F1 vs F2 vs constrained recall | Recall at fixed FPR |
| 3 | Feature ablation | remove each feature individually | Delta-F1 per feature |
| 4 | Two-stage ensemble | auth recall stage + combined filter stage | F1, recall, FPR |
| 5 | Statistical significance | 5-10 runs, varied seed + window size | Mean +/- std, p-values |

These five experiments will harden the methodology by establishing fair baseline comparisons across both datasets, validating feature choices, optimizing the detection threshold for the security domain, exploring ensemble strategies, and establishing statistical confidence in the results.
