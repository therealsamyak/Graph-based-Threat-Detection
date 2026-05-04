## 3. Deeper Cross-Dataset Analysis

### Cross-Dataset Protocol Convergence

Both DAPT2020 and LANL show that attack traffic overwhelmingly favors TCP, despite differing data sources (simulation vs. real-world enterprise network).

| Source | Context | TCP | UDP | Other |
|---|---|---|---|---|
| DAPT2020 attacks | All stages combined (n=20,665) | 100.0% | 0.0% | 0.0% |
| DAPT2020 benign | Background traffic | 51.5% | 41.8% | 6.7% |
| LANL flows (1M sample) | Overall traffic | 84.1% | 11.1% | 4.9% |
| LANL redteam flows | C17693, C18025, C19932, C22409 (n=167,787) | 99.82% | 0.15% | 0.03% |

LANL red-team computers contacted these top destination ports:

| Port | Service | Flow Count |
|---|---|---|
| 445 | SMB | 589 |
| 139 | NetBIOS | 523 |
| 443 | HTTPS | 180 |
| 80 | HTTP | 157 |
| 21 | FTP | 137 |
| 22 | SSH | 75 |

Notably, TCP-only service ports (445, 22) account for only 664 of 167,787 red-team flows (0.4%) — red-team operators also target many non-standard ports, but still almost exclusively over TCP.

- Figure 8: `analysis/figures/cross_dataset_protocol_comparison.png` — shows protocol distributions across datasets

### Kill-Chain Stage Progression (DAPT2020)

| Stage | Flows | Unique Dst Ports | Mean Fan-Out | Median Duration (μs) | Top Port | Top Port Flows |
|---|---|---|---|---|---|---|
| Reconnaissance | 11,909 | 4,166 | 2.50 | 12,310 | 9000 (DVWA) | 2,566 |
| Establish Foothold | 8,604 | 4,378 | 2.67 | 184,900 | 9002 (BadStore) | 49 |
| Lateral Movement | 137 | 82 | 6.00 | 5,013,574 | 4444 (reverse shell) | 20 |
| Data Exfiltration | 15 | 10 | 1.00 | 3,546 | — | — |

**Key findings:**

- Lateral movement has the highest fan-out ratio (6.0 vs. 2.50–2.67 for reconnaissance and foothold) — attackers spread to more unique destinations per source during this stage
- Lateral movement has the longest median flow duration (~5M μs ≈ 5 seconds) — persistent sessions likely for credential reuse and tool deployment
- Exfiltration flows are short-lived (median 3,546 μs) with minimal fan-out (1.0), suggesting targeted data transfers

**Small sample caveat:** Lateral movement (n=137) and data exfiltration (n=15) have limited sample sizes. Findings for these stages are suggestive but should be interpreted cautiously.

**MITRE ATT&CK mapping:**

| Stage | Technique | ID |
|---|---|---|
| Reconnaissance | Network Service Discovery | T1046 |
| Establish Foothold | Exploit Public-Facing Application | T1190 |
| Lateral Movement | Remote Services / Lateral Tool Transfer | T1021 / T1570 |
| Data Exfiltration | Exfiltration Over C2 Channel | T1041 |

- Figure 9: `analysis/figures/kill_chain_stage_progression.png` — shows flow characteristics across kill-chain stages

### Temporal Fingerprinting

Attack behavior leaves distinct temporal signatures visible in inter-arrival times and flow durations.

**LANL auth inter-arrival times (from Analysis.md):**

- Normal user median: 6 seconds
- Red-team user median: 214 seconds (35.7× slower)

The 2M-sample analysis confirms the directional pattern (normal=7s, redteam=2s), though the magnitudes differ due to sampling — the 2M sample is drawn from 1B+ total rows, introducing sampling artifacts.

**DAPT2020 flow duration by stage:**

| Stage | Median Duration |
|---|---|
| Reconnaissance | 12,310 μs (~12 ms) |
| Establish Foothold | 184,900 μs (~185 ms) |
| Lateral Movement | 5,013,574 μs (~5.0 s) |
| Data Exfiltration | 3,546 μs (~3.5 ms) |

Flow duration increases by ~15× from reconnaissance to foothold, then by ~27× from foothold to lateral movement. This progression reflects the increasing session complexity at each kill-chain stage: quick scans → exploitation handshakes → persistent remote sessions.

- Figure 10: `analysis/figures/temporal_fingerprinting.png` — shows temporal patterns across datasets and attack stages

### TCP Dominance in Attack Traffic

Across both datasets, attack traffic is nearly or entirely TCP. This is consistent across both datasets and not an artifact of any single data source.

| Source | Attack TCP % |
|---|---|
| DAPT2020 all attack stages | 100.0% |
| LANL redteam computers | 99.82% |

**Why attacks are TCP-only:**

1. **Protocol requirements:** SMB (445), SSH (22), RDP (3389) — the primary lateral movement services — are all TCP-only by design. An attacker targeting these services has no UDP option.

2. **Session integrity:** Command execution, file transfers, and authentication handshakes all require guaranteed delivery. UDP's best-effort model is unsuitable for interactive sessions where dropped packets mean failed exploitation.

3. **Connection state:** Attackers benefit from TCP's connection-oriented nature for persistent C2 channels, detecting failed connections (closed ports/firewalls), and session reuse across multiple commands.

**Counter-evidence that UDP absence is not a simulation artifact:** DAPT2020 benign traffic is 41.8% UDP, confirming the simulation environment can and does produce UDP traffic. The attack tools simply do not use it. The LANL real-world data (99.82% TCP) independently confirms this pattern.

- Figure 11: `analysis/figures/protocol_by_attack_stage_detailed.png` — shows protocol breakdown by attack stage with benign comparison
