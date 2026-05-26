## Slide 1: Title

### Slide content
Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis of Flow and Authentication Logs

Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur  
ECE 239AS, UCLA

### Speaker notes
Open with the core framing: lateral movement happens after initial compromise, when an attacker pivots through internal machines toward higher-value targets. The project asks whether combining network flow logs and authentication logs inside one graph improves detection compared with using either source alone. Content-balanced speaker split: Ibrahim covers Slides 1–8 for framing, prior work, LANL scope, and graph construction; Wesley covers Slides 9–16 for variants, features, scoring, path/threshold logic, and baselines; Samyak covers Slides 17–24 for results, validation, ablations, limitations, and conclusion.

## Slide 2: Main Takeaways: Auth Logs and Graph Features Drive Detection

### Slide content
1. Authentication logs carry the strongest lateral-movement signal.
2. Graph-derived features explain most of the detection lift.
3. Weight optimization generalizes; the main value is interpretable scoring.

### Speaker notes
These are the three points to keep returning to. The combined graph is the main system, but the experiments show a sharper nuance: auth-only is extremely strong on LANL, graph features add substantial discriminative power, and Nelder-Mead is useful mainly because it gives a transparent weighted score rather than because it beats logistic regression.

## Slide 3: Internal Telemetry Is Split and Noisy

### Slide content
Internal cloud traffic is noisy, trusted by default, and split across separate telemetry sources.

### Speaker notes
Flow logs show who connected to whom, but not whether the connection was an attacker session or normal administration. Authentication logs show logons, but miss reconnaissance or service exploitation that never creates a login event. Perimeter IDS also sees mostly north-south traffic, while lateral movement is east-west inside the VPC.

## Slide 4: We Test Whether Graph Fusion Beats Single-Source Baselines

### Slide content
Can graph-based analysis of combined flow and authentication logs detect lateral movement better than single-source or tabular baselines?

### Speaker notes
The original proposal emphasized low latency and real-time processing. The implemented report centers on LANL-2015 evaluation: build graph variants from flow-only, auth-only, and combined logs, then compare them with unsupervised tabular anomaly detectors using aligned metrics.

## Slide 5: Prior Work Motivates Graphs; Our Test Fuses Auth and Flow

### Slide content
- Prior work detects paths, provenance, temporal links, or alert context.
- Our angle: unified auth + flow graph with interpretable edge/path scoring.

### Speaker notes
Use this slide to make the paper-presentation framing clearer. Hopper motivates login-graph path detection; Euler motivates temporal graph modeling; POIROT motivates provenance graphs but relies on known attack templates; HOLMES motivates multi-log kill-chain correlation. Kitsune and NoDoze motivate flow-feature baselines and rarity-based triage. Our difference is combining authentication and flow telemetry in one graph, then evaluating source ablations and tabular baselines on lateral-movement pairs.

## Slide 6: We Detect Post-Compromise Pivots, Not Initial Access

### Slide content
Assume one machine is already compromised; detect the pivoting behavior that follows.

### Speaker notes
The attacker may scan internal hosts, reuse credentials, SSH or RDP into machines, use SMB, or exploit services. The goal is not initial access detection. It is detecting source-destination pairs that match red-team lateral movement behavior after foothold.

## Slide 7: All Reported Results Use LANL-2015 Only

### Slide content
LANL-2015 only: 58 days, 1.6B+ events, 749 red-team events, 308 attack pairs.

### Speaker notes
LANL-2015 spans 58 days, 1.6B+ events, 749 red-team events, and 308 unique red-team source-destination pairs across authentication, flow, and red-team files. To avoid loading all events, the pipeline scopes to ±3,600 seconds around red-team events, merges overlaps into 25 intervals, and streams only events inside those windows. The presentation should be clear that every reported experiment and figure is LANL-only.

## Slide 8: The Graph Unifies Machines, Users, Auth Events, and Flows

### Slide content
Computers and users become nodes; auth events and flow records become directed edges.

### Speaker notes
Authentication records create computer-to-computer edges, and when user fields exist, user-to-user metadata edges. Flow records create computer-to-computer edges with protocol, ports, packets, bytes, duration, and timestamps. Duplicate source-destination events increment edge weight rather than becoming separate graph edges.

## Slide 9: Source Ablations Separate Fusion From Single-Source Signal

### Slide content
- `combined`: authentication + flow edges
- `auth_only`: authentication edges only
- `flow_only`: flow edges only

### Speaker notes
These variants answer the key source-ablation question. If combined wins, multi-source correlation matters. If auth-only wins, authentication semantics dominate. If flow-only is weak, network connectivity alone is not enough for this dataset.

## Slide 10: Features Span Connection, Host, and Network Behavior

### Slide content
23 unique features across connection, host, and network levels.

### Speaker notes
Connection features include edge rarity, NTLM, network logon, auth success, lateral-movement ports, protocol rarity, byte-per-packet ratio, and duration. Host features include degree, fan-out ratio, betweenness, inter-arrival statistics, burst score, and active duration. Network features include density, clustering, components, node count, and edge count.

## Slide 11: NTLM and Graph Degree Dominate Single-Feature Signal

### Slide content
![Feature audit – auth only](feature_audit_auth_only.png)  
![Feature audit – combined](feature_audit_combined.png)  
![Feature audit – flow only](feature_audit_flow_only.png)

- How to read: x-axis = ROC AUC; y-axis = candidate feature; each panel is one graph variant; dashed 0.5 = random ranking.
- Takeaway: NTLM/network-logon semantics and destination degree are the strongest single-feature signals.

### Speaker notes
Use the figure to define AUC as the probability that a randomly chosen red-team edge ranks above a benign edge. Emphasize the top combined-variant features: `is_ntlm` at 0.933, `dst_in_degree` at 0.819, `is_network_logon` at 0.817, `dst_total_degree` at 0.812, and `edge_rarity` at 0.809. The point is not that one feature solves the problem; it is that authentication semantics plus graph structure are the right signal family.

## Slide 12: Nelder-Mead Makes the Score Interpretable

### Slide content
Nelder-Mead learns feature weights by maximizing ROC AUC over labeled red-team pairs.

### Speaker notes
Drafts supersede the final report here. The final approach is not hand-tuned feature weights. It uses a derivative-free Nelder-Mead simplex search over a weighted sum. Non-binary features are percentile-ranked to reduce outlier influence; binary features pass through unchanged.

## Slide 13: Edge Scores Are Weighted Sums Over Audited Features

### Slide content
`s = Σ wᵢ* · fᵢ`

### Speaker notes
For the combined variant, the selected features are `is_ntlm`, `dst_in_degree`, `is_network_logon`, `dst_total_degree`, and `edge_rarity`. In the formula, the star on `wᵢ*` means the weight was optimized rather than hand-picked. Auth-only uses `src_in_degree`, `is_ntlm`, and `src_out_degree`. Flow-only uses `src_burst_score`, `dst_inter_arrival_mean`, and `dst_inter_arrival_std`. User-account edges and self-loops receive score 0 because they carry no red-team signal in the labeled data.

## Slide 14: Path Boosting Adds Multi-Hop Context

### Slide content
Single suspicious edges are not enough; lateral movement is often multi-hop.

### Speaker notes
The pipeline enumerates paths up to 4 hops with BFS, following only the top 10 outgoing edges per node by edge score. Each path score averages three views: geometric mean, maximum edge score, and arithmetic mean. The top 50 paths are kept, and edges in those paths receive a 0.1 × path-score boost capped at 1.0.

## Slide 15: Thresholds Are Chosen in Pair-Space for F1

### Slide content
Sweep percentiles `{90, 95, 97, 99, 99.5, 99.9}` and choose the best F1.

### Speaker notes
Metrics are computed in pair-space: after thresholding edges, anomalous edges collapse into source-destination pairs and are compared with red-team pairs. If all edge scores have zero variance, the threshold is set above the maximum score so no edges are flagged.

## Slide 16: Baselines Use the Same Feature Vectors for Fair Comparison

### Slide content
Compare graph scoring against One-Class SVM and Isolation Forest on the same edge features.

### Speaker notes
One-Class SVM uses an RBF kernel with `nu=0.1`; Isolation Forest uses 100 trees, `contamination="auto"`, seed 42. Both train only on normal edges, evaluate on held-out normal edges plus red-team edges, and use the same threshold optimizer and pair-metric calculator as the graph detector.

## Slide 17: Combined Graph Ranks Best While Keeping Alert Cost Low

### Slide content
![Method comparison – AUC](method_comparison_auc.png)  
![Method comparison – F1](method_comparison_f1.png)  
![Method comparison – Recall](method_comparison_recall.png)

- How to read: x-axis = graph variant; y-axis = metric score; each panel is one metric (AUC, F1, recall); colors = detector.
- Takeaway: graph scoring gives the best combined-variant AUC; Isolation Forest buys recall with more alert cost.

### Speaker notes
AUC is threshold-independent ranking quality; F1 combines precision and recall; recall is the fraction of red-team pairs found. The draft result summary says the combined graph method achieves AUC 0.959 with FPR 0.004. Isolation Forest detects more red-team pairs in the combined setting, but its higher false-positive rate means more analyst burden. Present this as a tradeoff, not a universal win.

## Slide 18: Auth-Only Is Strongest in LANL; Flow-Only Is Not Actionable

### Slide content
Auth-only: AUC 0.984, recall 0.922, FPR 0.006.  
Combined: AUC 0.959, recall 0.211, FPR 0.004.  
Flow-only: AUC 0.963, recall 0.068, FPR 0.030.

### Speaker notes
This is the most important nuanced result. Authentication-only catches most red-team pairs in LANL because NTLM and network-logon behavior are highly informative. Combined has the lowest false positive rate but lower recall at its selected threshold. Flow-only can rank some edges well but has poor operating-point recall, making it weak as a standalone detector.

## Slide 19: Optimized Weights Generalize on Held-Out Edges

### Slide content
![Held-out validation](holdout_validation.png)

- How to read: x-axis = variant; y-axis = AUC; bars = optimizer evaluation, logistic-regression evaluation, optimizer calibration.
- Takeaway: calibration and held-out AUC stay nearly identical, so optimized weights are not just memorizing.

### Speaker notes
Calibration means the half used to fit weights; evaluation means the held-out half. The held-out split has calibration AUC 0.9646 and evaluation AUC 0.9630, a gap of only 0.0016 or 0.17%. The equal-weight baseline is about 0.9101, so optimized weights improve ranking without a meaningful held-out penalty.

## Slide 20: Logistic Regression Matches Nelder-Mead, So Features Drive Lift

### Slide content
Nelder-Mead eval AUC: 0.9630.  
Logistic regression eval AUC: 0.9624.

### Speaker notes
The supervised linear method barely changes the outcome. Logistic regression and Nelder-Mead agree within single-seed noise. So the optimizer should be presented as an interpretable scoring mechanism aligned with the project’s formula, not as a novel learner outperforming standard supervised models.

## Slide 21: Graph Features Explain Most of the AUC Gain

### Slide content
![Ablation study](ablation_study.png)

- How to read: x-axis = feature family; y-axis = evaluation AUC; colors = graph variant.
- Takeaway: graph-derived features outperform pure tabular features and explain most of the gain.

### Speaker notes
Pure tabular features reach eval AUC 0.9529. Graph-derived features alone reach 0.9867. Combined features reach 0.9904. Adding graph-derived features on top of tabular raises eval AUC by 0.0375, while adding tabular features on top of graph features adds only 0.0037. This is the strongest evidence that representation, not optimizer choice, drives the result.

## Slide 22: Representation Matters More Than Optimizer Choice

### Slide content
Detection lift comes from feature representation more than the optimizer.

### Speaker notes
The evaluation decomposes the improvement. Supervised learning on tabular features is one contribution. Graph-derived local features add another roughly +0.037 AUC. Label-free multi-hop features add a modest +0.015. Known-attacker propagation can add +0.036, but only when a compromised seed is known.

## Slide 23: Lots of Future Work Left to be Done

### Slide content
- Runtime and scalability: latency, throughput, CPU/memory profiling on stream-scale data.
- New datasets: evaluate on cloud-native VPC flow logs (AWS VPC Flow, Azure NSG, GCP VPC) to test generalization beyond LANL.
- Industry partnership: collaborate with a cloud provider for real deployment telemetry and live red-team exercises.
- Streaming graph: incremental graph updates instead of batch rebuilds for true real-time detection.
- Adaptive thresholds: drift-aware threshold tuning as network baseline shifts over time.

### Speaker notes
This project evaluated on LANL-2015 only, so the most important next step is testing on modern cloud environments. Partnering with a cloud network provider would give access to real VPC flow logs and authentication telemetry at production scale, plus the ability to run controlled red-team exercises. On the systems side, we have not measured latency or throughput — the current pipeline is batch-oriented, so profiling ingest-to-alert time and memory usage under streaming conditions is essential before any deployment claim. Incremental graph updates (adding edges without rebuilding the whole graph) would be needed for true real-time operation. Threshold drift is another practical concern: as network behavior evolves, fixed percentile thresholds may degrade, so adaptive or drift-aware methods are worth exploring.

## Slide 24: Conclusion: Auth Semantics and Graph Features Drive Detection

### Slide content
1. Authentication logs carry the strongest lateral-movement signal.
2. Graph-derived features explain most of the detection lift.
3. Weight optimization generalizes; the main value is interpretable scoring.

### Speaker notes
Restate the same takeaways from Slide 2. The project’s strongest claim is not simply “combined logs always win.” The more precise claim is that graph-based representations of auth and flow telemetry expose relational patterns that tabular methods miss, while auth semantics dominate this LANL evaluation.
