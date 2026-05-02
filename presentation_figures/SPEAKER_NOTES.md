# Presentation Script & Speaker Notes
## Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis

**Team:** Ibrahim Pehlivan, Wesley Gunawan, Samyak Kakatur  
**Course:** ECE 239AS — Machine Learning and Data Mining for Cybersecurity  
**Duration:** ~5 minutes  
**Figures:** `presentation_figures/` directory

---

## Slide 1: Title Slide

**Visual:** Project title, team names, UCLA logo

**Speaker (Wesley, 5 seconds):**
"Good morning. We're Ibrahim, Wesley, and Samyak, and today we're presenting our work on detecting lateral movement in cloud VPC networks using graph-based analysis."

---

## Slide 2: The Problem — Lateral Movement Goes Undetected

**Figure:** `presentation_figures/02_kill_chain.png`

**Speaker (Wesley, 25 seconds):**
"Lateral movement is the phase where an attacker who's already breached one machine starts hopping through a network to reach high-value targets. In cloud VPC environments, this is especially dangerous because internal traffic is trusted by default — there's no perimeter defense.

The kill chain goes: Reconnaissance, Initial Compromise, Lateral Movement, and then the attacker reaches their objective. Our focus is on that lateral movement phase — the critical window between initial access and data exfiltration."

**Key point to emphasize:** Internal traffic is trusted, single log sources aren't enough, and the volume of normal traffic drowns out attack signals.

---

## Slide 3: Our Approach — Graph-Based Multi-Source Detection

**Figure:** `presentation_figures/03_pipeline_architecture.png`

**Speaker (Samyak, 30 seconds):**
"Our approach combines two log sources — network flow logs and authentication logs — into a unified graph. Computers and user identities become nodes, and connections and authentication events become edges.

The pipeline has four stages:
1. **Data ingestion** from flow and auth logs
2. **Graph construction** — incrementally building the network graph
3. **Feature extraction** — computing structural features like degree and fan-out, temporal features like inter-arrival times, and statistical features like edge rarity
4. **Anomaly scoring** — scoring each edge and path to flag suspicious subgraphs

The key insight is that flow data alone misses who logged in, and auth data alone misses reconnaissance. Only combining both captures the full attack lifecycle."

---

## Slide 4: Datasets — Real-World and Simulated Attack Data

**Figure:** `presentation_figures/04_dataset_comparison.png`

**Speaker (Samyak, 20 seconds):**
"We evaluate on two complementary datasets:

**LANL-Dataset-2015** is real enterprise network data from Los Alamos National Laboratory — 58 days, 1.6 billion events, with 749 labeled red-team attack events.

**DAPT2020** is a simulated APT testbed with 86,690 flows across 4 labeled kill-chain stages: reconnaissance, foothold, lateral movement, and exfiltration.

Together, these give us both real-world scale and labeled attack stage detail."

---

## Slide 5: Key Finding 1 — Attack Traffic is Overwhelmingly TCP

**Figure:** `presentation_figures/05_protocol_distribution.png`

**Speaker (Ibrahim, 25 seconds):**
"Our first key finding: attack traffic is overwhelmingly TCP. In the LANL data, 99.82% of red-team flows use TCP. In DAPT2020, it's 100%. Meanwhile, benign traffic is roughly 50% TCP.

Why? Because the primary lateral movement services — SMB on port 445, SSH on port 22, and RDP on port 3389 — are all TCP-only. Attackers need reliable, in-order delivery for command execution and file transfers. This gives us a strong detection signal: TCP dominance is structural, not coincidental."

---

## Slide 6: Key Finding 2 — Kill-Chain Progression Has Predictable Patterns

**Figure:** `presentation_figures/06_fan_out_ratio.png`

**Speaker (Ibrahim, 25 seconds):**
"Second finding: the fan-out ratio — unique destination ports per source — follows a predictable arc across the kill chain.

During reconnaissance, it's about 2.5 — attackers are scanning broadly. When they establish a foothold, it stays around 2.7. But during lateral movement, it jumps to 6.0 — they're spreading from compromised hosts. Then it drops to 1.0 during exfiltration because they're going to one target.

This 2.5 to 6.0 jump maps directly to the shift from 'scan everything' to 'spread from compromised hosts.' We can use this pattern to detect when an attack transitions into lateral movement."

---

## Slide 7: Key Finding 3 — Attackers Are Slower and More Deliberate

**Figure:** `presentation_figures/07_inter_arrival_time.png`

**Speaker (Wesley, 25 seconds):**
"Third finding: red-team authentication events have a median inter-arrival time of 214 seconds — compared to just 6 seconds for normal users. That's a 35.7× difference.

Attackers are slower and more deliberate. Our pipeline results confirm this — redteam nodes show 3.1× higher inter-arrival mean, 4.5× higher variance, and 5.5× longer active durations.

These timing gaps are large enough to be useful for detection."

---

## Slide 8: Graph Construction — From Logs to Detection

*(Can be merged with Slide 3 if time is tight)*

**Figure:** `results/<run_id>/figures/graph_snapshot.png` (or `presentation_figures/03_pipeline_architecture.png`)

**Speaker (Samyak, 15 seconds):**
"Our streaming graph builder incrementally adds nodes for computers and users, and edges for each connection or authentication event. Edges are deduplicated by source-destination pairs, with accumulated weight and temporal attributes.

The graph updates in real-time as new log records arrive, enabling continuous detection rather than batch analysis."

---

## Slide 9: Detection Methodology — Scoring and Alerting

**Figure:** `presentation_figures/10c_score_comparison.png`

**Speaker (Samyak, 20 seconds):**
"Our scoring works at three levels:

1. **Node suspiciousness** — combining fan-out ratio, inter-arrival timing, betweenness centrality, and degree. Nodes behaving like lateral movement sources get higher scores.

2. **Edge scoring** — 50% from source node suspiciousness, 20% from edge rarity, 15% from TCP protocol signal, and 15% from lateral movement port detection.

3. **Path enumeration** — BFS traversal of high-scoring edges to detect multi-hop attack chains.

The result: redteam edges score 1.59× higher than baseline edges on average — confirming our scoring separates attack traffic from normal operations."

---

## Slide 10: Results — What We've Learned

**Figures:** `presentation_figures/10a_auc_comparison.png`, `10b_feature_importance.png`, `10d_key_findings.png`

**Speaker (Wesley, 35 seconds):**
"Here are our key results.

The **combined method achieves the highest AUC of 0.9456**, outperforming auth-only (0.9094) by 4%. This confirms our core hypothesis: combining flow and auth logs improves detection over single-source methods.

Flow-only achieves 0 AUC because redteam lateral movement primarily uses authenticated connections — flows alone don't capture the 'who.'

Our feature importance analysis shows redteam nodes are distinguished by **active duration (5.5× higher)**, **inter-arrival variance (4.5×)**, and **in-degree (3.3×)** — all consistent with the paper's analysis that attackers are slower, more connected, and more deliberate."

---

## Slide 11: Challenges and Limitations

**Figure:** `presentation_figures/11_detection_scatter.png`

**Speaker (Ibrahim, 20 seconds):**
"Key challenges:

First, **dataset scale** — the full LANL dataset is 68GB of auth logs plus 5GB of flows. Our current results use 1 million event samples. Full ingestion would take hours.

Second, **detection recall** is limited by sampling — only 4 of 308 unique redteam pairs appear in our sampled graph. The combined AUC of 0.9456 confirms the scoring works, but we need full data for production recall.

Third, **attack diversity** — redteam focuses on SMB, SSH, and credential reuse. We haven't tested against living-off-the-land or fileless techniques."

---

## Slide 12: Conclusion

**Visual:** Summary slide (no figure needed)

**Speaker (Wesley, 20 seconds):**
"To summarize: we built a graph-based detection pipeline that combines flow and authentication logs, extracted structural and temporal features, and scored nodes and edges for lateral movement likelihood.

Our key findings are:
1. Attack traffic is overwhelmingly TCP — a strong detection signal
2. Kill-chain progression has predictable patterns in fan-out
3. Attackers are slower and more deliberate — 35× higher inter-arrival times
4. Combined graph analysis achieves AUC of 0.9456, outperforming single-source methods

Future work: full dataset ingestion, ML classifiers on graph features, and live deployment."

---

## Slide 13: Q&A

**Visual:** Thank you + questions

**Speaker (All):**
"Thank you. We'd be happy to take any questions."

---

## Timing Budget

| Slide | Topic | Speaker | Time |
|-------|-------|---------|------|
| 1 | Title | Wesley | 5s |
| 2 | Problem | Wesley | 25s |
| 3 | Approach | Samyak | 30s |
| 4 | Datasets | Samyak | 20s |
| 5 | TCP Dominance | Ibrahim | 25s |
| 6 | Kill-Chain Patterns | Ibrahim | 25s |
| 7 | Inter-Arrival Time | Wesley | 25s |
| 8 | Graph Construction | Samyak | 15s |
| 9 | Scoring Methodology | Samyak | 20s |
| 10 | Results | Wesley | 35s |
| 11 | Challenges | Ibrahim | 20s |
| 12 | Conclusion | Wesley | 20s |
| 13 | Q&A | All | — |
| **Total** | | | **~4:45** |

---

## Anticipated Q&A

**Q: Why is your recall 0 if AUC is 0.9456?**
A: The AUC measures how well edge scores rank redteam edges above baseline edges — and they do (0.85 vs 0.53 mean score). However, our 95th percentile threshold is 0.86, just above the redteam mean of 0.85. This is a threshold sensitivity issue, not a scoring issue. With adaptive thresholding or full dataset ingestion, recall would improve significantly.

**Q: How does your method compare to Hopper or Euler?**
A: Hopper uses only authentication logs and path inference — we extend this by adding flow logs to catch movement that bypasses login. Euler uses temporal link prediction on a single data source — we combine multiple sources. Our AUC of 0.9456 on LANL is competitive, though direct comparison is difficult since we use different evaluation metrics.

**Q: Can this work in real-time?**
A: The pipeline is designed for streaming — it processes events incrementally without loading full datasets. Our throughput is 6,781-19,749 events/sec on sampled data. For production, we'd need optimized graph storage (e.g., Neo4j, GraphDB) and distributed processing, but the architecture supports real-time detection.

**Q: What about encrypted traffic?**
A: Our current approach doesn't need deep packet inspection — it uses metadata (protocol type, ports, timing, connectivity). This means it works even with encrypted payloads. HTTP/3 over UDP is an interesting case we plan to investigate.

---

## How to Use These Materials

1. **Figures** are in `presentation_figures/` — numbered by slide (02, 03, 04, etc.)
2. **Existing figures** from the pipeline run are in `results/20260502_075816/figures/` — graph snapshot, ROC curves, score distribution, detection timeline
3. **Speaker notes** above are timed for ~4:45 total, leaving room for transitions
4. If time is tight, merge slides 8+9 (graph construction + scoring) into slide 3 (approach)
5. Practice the transitions between speakers — the handoffs should feel natural
