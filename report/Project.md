# Proposal 1: Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis of Flow and Authentication Logs

## Background Motivation

Lateral movement is the phase of an attack where someone who already got into one machine starts hopping to others on the same network. It is hard to catch in cloud environments because internal traffic is noisy, constantly changing, and mostly trusted by default. The telemetry itself is also split across different sources (VPC Flow Logs over here, auth logs over there), so piecing together what actually happened across multiple steps is not straightforward.

## Research Question

Can graph-based analysis of combined VPC flow logs and authentication logs detect lateral movement accurately and with low latency?

### Sub-Research Questions

1. How do you merge different cloud log types (flow, auth) into one graph without losing the timing and context that matter?
2. Which graph features (structural, temporal, statistical) actually separate lateral movement from routine service traffic?
3. Does combining flow and authentication logs meaningfully improve detection compared to using either one alone?

## Proposed Methodology

### Data

All data is generated through a controlled cloud deployment (AWS or GCP) rather than pulled from a static dataset.

We use VM instances inside a single VPC, with VPC Flow Logs and authentication logs (IAM, SSH, API calls) enabled.

There are 2 main 'workloads' simulated:

- **A simulated multi-tier application (normal / baseline workload)**
  - Ex. "Web server → app server → database"
  - This produces HTTP requests, internal service-to-service communication, and periodic admin SSH access.
  - This is a baseline that defines expected behavior.
- **Attack workload** executed from a designated "compromised" VM. This could use:
  - Internal port scanning (high fan-out connections)
  - SSH-based lateral movement across instances
  - Credential reuse across machines
- All attack time intervals are manually recorded as ground truth labels for evaluation.

### Compute Resources

- GCP (or other cloud providers like Oracle) free tier for VM deployment and logging.
- One analysis node (local machine or cloud VM) for processing
- Optionally a lightweight streaming pipeline for log ingestion

### Techniques

- **Streaming graph construction.**
  - Nodes are VM instances and user identities.
  - Edges are network connections (from flow logs) and authentication events (from identity logs).
  - A time-windowed dynamic graph is maintained and updated as logs arrive.
- **Feature extraction.**
  - Structural features: node degree, fan-out, new edge rate.
  - Temporal features: inter-arrival times, burst patterns.
  - Statistical features: edge rarity and deviation from the established baseline.
- **Detection.**
  - Single-source (VPC logs only, authentication logs only) methods for control / baseline
  - Proposed combination method (VPC + auth logs using the graph) that "scores" multi-hop sequences based on features
- **Real-time processing.**
  - Continuous log ingestion and incremental graph updates
  - Anomaly scoring and alert generation happening with minimal delay.

### Evaluation

- Detection rate (recall) measured against labeled attack intervals
- False positive rate on normal workload
- Detection latency from the moment an attack begins
- Throughput (events processed per second)
- System overhead (CPU and memory usage)
- Compare combination method with single-source. If possible, measure the contribution of each source within the combination method to see if one is better than the other.

## Related Works

### 1. Hopper: Modeling and Detecting Lateral Movement

- **Link:** <https://arxiv.org/abs/2105.13442>
- **Summary:** Hopper builds a graph of login activity and catches lateral movement by looking for suspicious sequences of logins. It uses path inference and anomaly scoring, and gets high accuracy because it looks at multi-step behavior rather than single events.
- **Relevance:** This project extends Hopper by folding in network flow logs, which lets us catch lateral movement that does not go through authentication at all.

### 2. POIROT: Aligning Attack Behavior with Kernel Audit Records for Cyber Threat Hunting

- **Link:** <https://arxiv.org/abs/1910.00056>
- **Summary:** POIROT builds provenance graphs from audit logs and matches them against known attack templates. It identifies multi-stage campaigns by aligning observed activity with attack graphs.
- **Relevance:** This project builds on the multi-log graph idea but swaps template matching for anomaly detection and adapts the whole thing to cloud-native logs.

### 3. Euler: Detecting Network Lateral Movement via Scalable Temporal Graph Link Prediction

- **Link:** <https://www.ndss-symposium.org/ndss-paper/euler-detecting-network-lateral-movement-via-scalable-temporal-graph-link-prediction/>
- **Summary:** Euler models enterprise networks as temporal graphs and uses self-supervised link prediction to identify anomalous network connections indicative of lateral movement. It is designed to handle highly dynamic network environments and scales efficiently to process millions of connection and authentication events.
- **Relevance:** This paper directly supports our proposed technique of maintaining a time-windowed dynamic graph to score multi-hop sequences, providing a strong state-of-the-art baseline for temporal graph feature extraction.

### 4. HOLMES: Real-time APT Detection through Correlation of Suspicious Information Flows

- **Link:** <https://arxiv.org/abs/1810.01594>
- **Summary:** HOLMES creates a high-level kill-chain graph by correlating system audit logs, mapping low-level events directly to MITRE ATT&CK tactics like lateral movement and privilege escalation. It uses a dynamic real-time scoring system to raise alerts only when enough correlated evidence of a multi-stage attack accumulates, significantly reducing noise.
- **Relevance:** This validates our goal of correlating diverse log sources (flow and authentication) into a unified graph and informs our real-time anomaly scoring methodology to minimize false positives.

### 5. Kitsune: An Ensemble of Autoencoders for Online Network Intrusion Detection

- **Link:** <https://arxiv.org/abs/1802.09089>
- **Summary:** Kitsune is an unsupervised, plug-and-play neural network system that monitors network traffic to detect attacks in real-time by analyzing statistical flow data. It continuously extracts temporal and structural features from network flows to identify anomalous behaviors and state changes without requiring pre-labeled data.
- **Relevance:** Kitsune's feature extraction methodology provides a proven, highly efficient framework for the network flow features we plan to calculate for our single-source (VPC logs only) baseline detection method.

### 6. NoDoze: Combatting Threat Alert Fatigue with Automated Provenance Triage

- **Link:** <https://www.ndss-symposium.org/ndss-paper/nodoze-combatting-threat-alert-fatigue-with-automated-provenance-triage/>
- **Summary:** NoDoze reduces false positives in threat hunting by scoring the anomalousness of system events based on the historical frequency and baseline of related execution paths. It constructs dependency graphs to provide context to isolated alerts, drastically lowering the burden on security analysts by filtering out benign administrative behavior.
- **Relevance:** This research directly addresses our sub-research question regarding false positive rates on normal workloads, offering a technique to assign statistical rarity scores to the edges in our proposed combined log graph.
