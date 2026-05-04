# Updated Mid-Point Presentation Layout

## Slide 1: Title Slide

- Title: "Real-Time Detection of Lateral Movement in Cloud VPC Networks via Graph-Based Analysis"
- Team member names
- Course info (ECE 239) and date

### Speaker Notes

- Introduce yourselves briefly — names and roles
- Set the stage: "We're working on detecting a specific type of cyber attack called lateral movement inside cloud networks"
- Don't spend more than 10 seconds here

## Slide 2: Key Takeaways

- **The Problem**: Lateral movement in cloud networks is hard to detect because no single log source tells the full story — attacks hide across billions of trusted internal events
- **Our Approach**: We model network traffic as graphs, scoring paths and subgraphs to flag anomalous behavior — no ML training, fully interpretable
- **The Data**: Real-world and simulated datasets (LANL, DAPT2020) contain structured flow and auth logs with labeled attacks — exactly the relational data needed to build meaningful graphs
- These 3 bullets frame the entire talk as a problem → solution → evidence story

### Speaker Notes

- Read through the 3 bullets clearly — this is your roadmap for the audience
- After reading each bullet, pause for a beat so they sink in
- Say something like: "I'll walk through each of these — first the problem, then our approach, then the data that makes it possible"

## Slide 3: What is Lateral Movement in Cloud Networks?

- Define VPC (Virtual Private Cloud) — a logically isolated section of a cloud network where internal traffic is trusted by default
- Show a simplified kill-chain diagram: Reconnaissance → Foothold → **Lateral Movement** → Exfiltration
- Concrete example: "After compromising one machine, an attacker pivots to other machines inside the VPC to escalate privileges and reach the target"
- Why this phase matters: it's the longest phase of an attack and the best window for detection

### Speaker Notes

- A VPC is like a private office building — everything inside is trusted, but once someone gets in, they can move between rooms freely
- The kill chain is the standard framework for how attacks progress: recon (scouting), foothold (getting in), lateral movement (moving around inside), exfiltration (stealing data)
- Lateral movement is the "moving between rooms" phase — the attacker already has access to one machine and is trying to reach more valuable targets
- Example to say aloud: "Imagine an attacker compromises an employee's laptop. From there, they SSH into a database server, then pivot to a backup server, then reach the crown jewels — that chain of hops is lateral movement"
- This is the longest phase of most breaches — sometimes lasting weeks or months — so it's the best opportunity to catch the attacker

## Slide 4: Why It's Hard to Detect

- Security tools focus on the perimeter — internal east-west VPC traffic is implicitly trusted
- Single log sources are insufficient — flow logs show connections but not who logged in; auth logs show logins but not what was accessed
- Volume drowns out signals — 1.6B+ events in LANL alone make manual inspection impossible
- Visual: simple diagram showing "flow log alone misses auth context" vs "auth log alone misses recon" vs "combined view fills gaps"

### Speaker Notes

- "Perimeter" means the boundary between the company network and the internet — firewalls and IDS watch that boundary closely, but traffic between machines inside the VPC (east-west) is usually unchecked
- Flow logs are like phone records — they show "computer A connected to computer B on port 443" but not who was behind it or whether it was authorized
- Auth logs are like badge swipes — they show "user X logged into computer Y" but not what they did afterward or what other machines they contacted
- Neither log alone gives you the full picture — you need both to trace the full path of an attacker
- "East-west traffic" means machine-to-machine traffic inside the network, as opposed to "north-south" which is traffic in and out of the network boundary
- The volume point: LANL's dataset has 1.6 billion events in 58 days — even if only 0.001% are attacks, that's still thousands of events to find in a haystack

## Slide 5: Two Complementary Datasets Ground Our Work

- LANL-2015: real enterprise network, 58 days, 1.6B+ events, 749 labeled red-team events
- DAPT2020: simulated APT testbed, 5 days, 20,665 attack flows, per-flow kill-chain labels
- Visual: simple 2-column comparison table (Type, Size, Attack Labels, Log Sources)
- Using both lets us validate on real data while testing under diverse controlled conditions

### Speaker Notes

- LANL = Los Alamos National Laboratory — they ran a red team exercise (simulated attack) on their real network and released the data. The 749 labeled events are ground truth for which connections were part of the attack
- DAPT2020 = a research testbed that simulates Advanced Persistent Threats (APTs — sophisticated, long-running attacks). It has per-flow labels telling you exactly which kill-chain phase each flow belongs to
- Why both matter: LANL is "real" but only has one type of label (red-team vs. normal), DAPT2020 is simulated but has richer labels (recon vs. foothold vs. lateral movement vs. exfiltration per flow)
- Both datasets have the right structure for graph construction — they contain source/destination pairs, timestamps, and authentication events that naturally form nodes and edges
- LANL has both flow and auth logs, which is rare — most public datasets only have one or the other

## Slide 6: We Model Network Traffic as Graphs

- Nodes = computers (IPs) and user identities (accounts); edges = network connections from flow + auth logs
- Each edge is enriched with structural, auth-specific, flow-specific, and temporal features (see next slide)
- Two complementary log sources: flow data captures network activity, auth data captures login events — neither alone is sufficient
- Visual: simple graph with ~5 nodes, labeled "computer" and "user" types, colored edges for each log source

### Speaker Notes

- "Degree" of a node = how many connections it has — a machine suddenly talking to 50 others instead of its usual 5 is suspicious
- "Centrality" = how important a node is in the overall network — a machine that sits on many paths between other machines (a "hub") is a high-value target or attacker staging point
- "Fan-out" = how many unique destinations a source connects to — normal users talk to a few servers, attackers scan many
- "Protocol rarity" = whether the connection uses an uncommon protocol for that pair — e.g., SSH between two machines that normally only communicate over HTTP
- "Edge rarity" = whether this specific connection (source → destination) has been seen before — new connections are more suspicious than recurring ones
- Think of the graph like a social network: people (users) and places (computers) are nodes, interactions are edges, and we're looking for suspicious social circles

## Slide 7: 23 Unique Features

We extract 23 unique features. Some are computed at different granularities (per-connection, per-host, per-snapshot) but all represent distinct signals. Node-level degree features (in_degree, out_degree) are also stamped onto edges as src_out_degree and dst_in_degree so that flat baselines can use them — these are the same signal, not new features.

**Connection features (11)** — computed per network connection:
- edge_rarity, is_self_loop, is_user_edge, is_ntlm, is_network_logon, is_success_auth, is_unusual_dst_port, protocol_rarity, byte_per_packet, duration_zscore, temporal_decay_weight

**Host features (7)** — computed per host (node):
- in_degree, out_degree, fan_out_ratio, betweenness_centrality, inter_arrival_mean, inter_arrival_std, burst_score, active_duration

**Network features (5)** — computed per network snapshot:
- density, avg_clustering, component_count, node_count, edge_count

All features are dataset-agnostic — computed from graph topology and edge attributes regardless of log source

### Speaker Notes

- 23 unique features. Some have derived variants (total_degree = in + out, src_out_degree = source node's out_degree projected onto edge) but these are math on existing features, not new signals
- Node features are extracted but currently NOT used in any scoring or baseline — only edge features feed detection. Node features are saved for future ablation studies
- Not all features are used in scoring — see next slides for which ones feed each method

**Connection features:**

- **edge_rarity**: 1/edge_weight → percentile rank. First-time or rare connections score highest. If A→B has been seen once vs. thousands of times, it's rare and suspicious
- **is_self_loop**: 1 if source = destination (computer connecting to itself). Almost never attack-related; used as a filter, not a signal
- **is_user_edge**: 1 if either endpoint is a user identity node. Filtered out during scoring
- **is_ntlm**: 1 if auth protocol is NTLM — older, weaker protocol attackers favor for relay and pass-the-hash attacks
- **is_network_logon**: 1 if logon type is "Network" (LogonType 3 = remote machine-to-machine auth). Primary vehicle for lateral movement
- **is_success_auth**: 1 if auth succeeded. Failed = possible brute-force; succeeded on suspicious path = confirmed compromise
- **is_unusual_dst_port**: 1 if port is SSH(22), Telnet(23), SMB(445), RDP(3389), WinRM(5985/5986), or ephemeral(>49152). Ports attackers use for remote access
- **protocol_rarity**: 1 − (fraction of all flow edges using that protocol). Uncommon protocols = more suspicious
- **byte_per_packet**: Bytes ÷ packets, percentile-ranked. Abnormal ratios suggest exfiltration or tunneling
- **duration_zscore**: Standard deviations from mean connection duration. Unusually long = backdoor; short = scanning
- **temporal_decay_weight**: Exponential decay so recent events score higher. Currently disabled (decay_rate=0 → always 1.0)

**Host features:**

- **in_degree / out_degree**: Incoming/outgoing connection counts for this host. A machine suddenly talking to 50 others instead of 5 is suspicious. These are projected onto edges as dst_in_degree and src_out_degree for flat baselines
- **fan_out_ratio**: out_degree / total_degree. Near 1.0 = mostly reaching out (scanning); near 0.0 = mostly receiving (server). Derived from in/out degree but captures a distinct behavioral pattern
- **betweenness_centrality**: How often this node sits on shortest paths between others. High = bridge/pivot point. Attackers naturally pass through high-betweenness nodes
- **inter_arrival_mean / inter_arrival_std**: Average and std dev of time gaps between this node's connections. Irregular timing = possible automated tools
- **burst_score**: Fraction of events in the busiest 10% time window. Sudden spike = scanning burst or mass exploitation
- **active_duration**: Total active time span (last − first event). Very long or short durations may be anomalous

**Network features:**

- **density**: Actual edges ÷ max possible edges. Sparse = anomalies stand out more
- **avg_clustering**: How tightly interconnected neighborhoods are. Low clustering + high degree = star topology (possible C2)
- **component_count**: Number of disconnected subgraphs. Changes reveal structural shifts
- **node_count / edge_count**: Size metrics for normalization

## Slide 8: Baselines — Flat Tabular Detection Without Graph Structure

- **Isolation Forest** (sklearn): unsupervised anomaly detector — randomly splits features, points isolated quickly are flagged as anomalous. Trained on normal-only data (n_estimators=100, contamination=0.05)
- **One-Class SVM** (sklearn): learns a boundary around normal data in feature space — anything outside is flagged. Trained on normal-only data (RBF kernel, nu=0.1)
- Both receive the same 12 edge features as a flat table (StandardScaler-normalized):
  - edge_rarity, src_out_degree, dst_in_degree, is_ntlm, is_network_logon, is_success_auth, source_fan_out, weight_norm, is_unusual_dst_port, protocol_rarity, byte_per_packet, duration_zscore
- Neither sees graph structure — no paths, no topology, no node/graph features
- Visual: simple diagram showing "edge feature vector → sklearn model → anomaly score" (flat pipeline, no graph)

### Speaker Notes

- Baselines treat each edge as an independent row in a spreadsheet — no awareness of which edges are connected or which nodes they share
- "Isolation Forest" works like 20 questions — if an edge is anomalous, you can "guess" it in very few random feature splits. Normal edges require many splits
- "One-Class SVM" draws a bubble around normal behavior — anything outside the bubble is suspicious
- Both are trained ONLY on normal data (no attack examples shown during training) — this is the standard for anomaly detection
- StandardScaler normalizes features to mean=0, std=1 before feeding to sklearn — prevents large-valued features from dominating
- Excluded from baselines: is_self_loop and is_user_edge (filtered out before training), temporal_decay_weight (not passed as feature)
- The 12 features include structural + auth + flow features — a fair comparison since baselines get MORE input features than the graph scorer
- Key limitation: baselines see edges as independent rows, so they can't detect multi-hop attack paths — that's the graph advantage

## Slide 9: Graph Scoring Explores Paths and Subgraphs

- Each edge gets a weighted anomaly score from a small subset of features:
  - Auth edges: is_ntlm (w=0.4) + is_network_logon (w=0.3) + edge_rarity (w=0.3)
  - Flow edges: edge_rarity (w=0.4) + is_unusual_dst_port (w=0.3) + protocol_rarity (w=0.3)
- Self-loops and user-identity edges are masked to score 0 (not attack-relevant)
- Edges are then aggregated into path scores and subgraph scores — a chain of slightly suspicious edges produces a strongly suspicious path
- Three scoring variants: flow-only, auth-only, and combined (both weighted together with auth_weight_multiplier=1.5)
- Visual: small graph with edges colored by score (green→yellow→red), a flagged path highlighted from source to destination

### Speaker Notes

- The graph scorer uses only 6 of 23 features — deliberately minimal. The other 17 are extracted but not yet incorporated into scoring (future ablation targets)
- Why only 6: these were the most discriminative features in initial analysis. is_ntlm flags weak auth protocols (attackers love NTLM), is_network_logon flags machine-to-machine connections, edge_rarity flags first-time connections
- "auth_weight_multiplier=1.5" means auth edges get a 50% boost over flow edges in combined mode — reflects that auth logs carry stronger attack signals
- Path scoring is the key differentiator: edges are not scored independently. A path A→B→C where each edge scores 0.3 becomes a path score of ~0.9 — the suspicion accumulates
- Subgraph scoring extends this: if a cluster of connected edges all score high, the whole region is flagged
- Self-loops (computer connecting to itself) and user-identity edges (user→user) are masked because they're almost never attack-related and would add noise
- These weights are currently hardcoded/arbitrary — this is exactly what we want to optimize with ablation studies and grid search

## Slide 10: LANL-2015 Results — Graph Scoring Outperforms ML Baselines

| Method | Features | AUC | Recall | FPR |
|---|---|---|---|---|
| Graph: combined (flow + auth) | 6 scored + path context | 0.954 | 0.662 | 0.020 |
| Graph: auth only | 3 scored + path context | 0.951 | 0.747 | 0.030 |
| Graph: flow only | 3 scored + path context | 0.579 | 0.013 | 0.030 |
| Isolation Forest (sklearn) | 12 flat edge features | 0.940 | 0.741 | 0.050 |
| One-Class SVM (sklearn) | 12 flat edge features | 0.706 | 0.492 | 0.098 |

- Graph combined beats Isolation Forest on AUC (0.954 vs 0.940) with half the FPR (0.020 vs 0.050)
- Flow-only barely above random (AUC 0.58) — validates single log source insufficiency
- All weights hardcoded — not yet optimized
- Takeaway: "Same hardcoded weights, strong signal on LANL — auth-based graph scoring is clearly effective"

### Speaker Notes

- "AUC" = how well the method separates attacks from normal traffic. 0.5 = random, 1.0 = perfect. 0.954 is strong
- "Recall" = fraction of attacks caught. 0.66 = ~2/3 caught
- "FPR" = fraction of normal traffic incorrectly flagged. 0.02 = 2% false alarms — in billions of events, still a lot
- Graph uses 6 features, baselines use 12 — graph wins despite fewer inputs because path scoring adds structural context
- Auth-only recall (0.747) beats combined (0.662) — suggests flow features may add noise at current weights
- Flow-only near random — single log source isn't enough, reinforcing the "why it's hard" message
- Proof of concept only — no feature selection or weight optimization yet

## Slide 11: DAPT2020 Results — Same Weights, Weaker Performance

| Method | Features | AUC | Recall | FPR |
|---|---|---|---|---|
| Graph: combined | 6 scored + path context | 0.601 | 0.222 | 0.019 |
| One-Class SVM (sklearn) | 12 flat edge features | 0.646 | 0.223 | 0.100 |
| Isolation Forest (sklearn) | 12 flat edge features | 0.449 | 0.007 | 0.050 |

- Same hardcoded weights that achieved AUC 0.954 on LANL drop to 0.601 here
- DAPT graph is 100x smaller (765 nodes vs 91,589) — fewer paths, less structural signal
- One-Class SVM slightly edges out graph scoring — suggests weights aren't tuned for this data
- Takeaway: "The approach transfers but the weights don't — per-dataset tuning or adaptive weighting is needed"

### Speaker Notes

- This slide directly follows the LANL results to highlight the gap — same pipeline, same weights, very different outcomes
- DAPT2020 has only 765 nodes and 1,502 edges vs. LANL's 91,589 nodes and 512,529 edges — the graph is too small for path scoring to find meaningful attack patterns
- Only 9 red-team pairs in the DAPT graph (vs 305 in LANL) — very few positive examples
- One-Class SVM (AUC 0.646) slightly beats graph (0.601) — this is expected when the graph is too small for structural scoring to help
- Isolation Forest drops to 0.449 (below random!) — likely because the DAPT feature distributions are very different from what the model expects
- The key insight: the graph-based APPROACH is sound (proven on LANL), but the WEIGHTS need per-dataset tuning
- This is exactly the motivation for ablation studies and adaptive weighting — future work

## Slide 12: What We've Learned So Far

- Combining log sources is critical — flow alone (AUC 0.58) vs. auth graph scoring (AUC 0.95)
- Simple weighted features on graph structure outperform ML baselines with more input features — the graph context matters more than the feature count
- Combined method has slightly lower recall than auth-only, suggesting flow features may add noise at this stage
- DAPT2020 is harder for our approach (AUC 0.60) — smaller graph, different attack patterns, same hardcoded weights

### Speaker Notes

- Auth-only outperforming combined is counterintuitive but informative — more data ≠ better results if the features aren't chosen carefully
- "Simple statistical features" = fan-out ratio, inter-arrival time, edge rarity — basic counts and ratios, not deep learning
- DAPT2020 being harder makes sense: its graph has only 765 nodes vs. 91,589 in LANL — fewer nodes means fewer paths, less structure for graph scoring to exploit
- The real insight: the problem isn't "can we detect attacks" — it's "can we detect attacks with low enough false positives to be useful in practice"

## Slide 13: Next Steps & Open Questions

- Systematic feature selection via ablation studies — which of the 23 features help vs. add noise
- Statistical validation with proper hypothesis testing, not just descriptive stats
- Scale to all 1.6B+ LANL events; tune weights via grid search or Bayesian optimization
- Open question: "Should we prioritize improving DAPT2020 performance or maximizing LANL results?"

### Speaker Notes

- "Ablation study" = remove one feature at a time and see how performance changes — tells you which features are actually contributing vs. adding noise
- "Statistical validation" means running proper tests (e.g., bootstrap confidence intervals, significance tests) to prove our findings aren't just luck
- Scaling to 1.6B events matters because our current results are on a subset — the full dataset may have different characteristics
- The open question is genuine: we want feedback on whether the audience thinks we should generalize (improve DAPT2020) or specialize (maximize LANL performance)

## Slide 14: Graph-Based Analysis Enables Fast, Interpretable Threat Detection

- Revisit takeaway 1 (problem): lateral movement hides in trusted internal traffic across billions of events — single logs can't catch it
- Revisit takeaway 2 (solution): graph-based scoring of multi-source log data detects attack paths without ML — interpretable and adjustable
- Revisit takeaway 3 (data): both datasets provide the structured relational logs needed to construct and score meaningful attack graphs
- "Graphs turn raw network logs into actionable attack paths — and we're just getting started"

### Speaker Notes

- Briefly restate each takeaway — don't read them word for word, paraphrase in 1-2 sentences each
- "Interpretable" means a security analyst can look at a flagged path and understand WHY it was flagged — which features contributed, which edges are suspicious — unlike a black-box neural network
- "Adjustable" means if a new attack pattern emerges, you can add a new feature or adjust weights without retraining a model
- End with the closing line confidently — it summarizes the value proposition in one sentence
- Leave a beat for questions
