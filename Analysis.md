# Pipeline Run Analysis — 2026-05-02

## Run Metadata

- **Run ID**: `20260502_070018`
- **Total wall time**: ~3h39m (00:00:18 → 03:39:06)
- **Command**: `make pipeline` → `uv run python run_experiment.py` (all defaults)
- **Results dir**: `results/20260502_070018/`

## Parameters Used

### Global (CLI)

| Parameter | Value | Source |
|---|---|---|
| `--data-dir` | `data/LANL-Dataset-2015` | default |
| `--window-size` | `3600` (1 hour half-window) | default |
| `--sample` | `None` (full dataset) | default |
| `--dapt-dir` | `data/DAPT2020` | default |

### Data Characteristics

| Source | Events Streamed |
|---|---|
| `flows.txt.gz` (flow_only) | 31,611,293 |
| `auth.txt.gz` (auth_only) | 104,073,656 |
| `auth.txt.gz` + `flows.txt.gz` (combined) | 104,073,656 auth + 31,611,293 flow |
| Red team events | 749 |
| Merged time windows | 25 |

### Graph Construction (`StreamingGraphBuilder`)

- **Edge deduplication**: Edges with same (src, dst) get `weight += 1`, keeping first_time/last_time
- **Node type inference**: `is_machine` inferred from `$` in name
- **User edges**: Auth events also create user→user edges (src_user → dst_user)
- **No edge time-windowing within graph**: All events within the 25 merged windows are added (massive windows → almost the entire dataset)

### Feature Extraction (`src/features.py`)

**Node features**: in_degree, out_degree, total_degree, fan_out_ratio, betweenness_centrality (only computed if ≤5000 nodes — skipped for auth_only and combined), inter_arrival_mean/std, burst_score, active_duration

**Edge features**: edge_rarity (1/weight), src_out_degree, dst_in_degree, is_ntlm, is_network_logon, is_success_auth, source_fan_out, weight_norm, is_self_loop, is_user_edge

**Graph features**: density, avg_clustering, component_count, node_count, edge_count

### Edge Scoring (`src/scorer.py`)

**Weights** (hardcoded defaults):
- `is_ntlm`: 0.4
- `is_network_logon`: 0.3
- `edge_rarity`: 0.3

**Scoring logic**:
- Auth edges: `0.4 * is_ntlm + 0.3 * is_network_logon + 0.3 * rarity_rank`
- Flow edges: `rarity_rank` only
- Self-loops and user edges: score forced to 0.0

### Path Enumeration

- **Max hops**: 4
- **Top-k paths returned**: 50
- **Top-k outgoing edges per node**: 10 (pruning)
- **Parallelism**: 12 workers (`ProcessPoolExecutor`)
- **Path score**: `(geometric_mean + max + mean) / 3` of edge scores

### Detection Threshold

- **Method**: 90th percentile of edge scores (excluding self-loops and user edges)
- Per-method thresholds: flow_only=0.8999, auth_only=0.7847, combined=0.843

### DAPT2020 Baselines

**OneClassSVM**: kernel="rbf", gamma="scale", nu=0.05, trained on normal-only samples, threshold=0.0

**IsolationForest**: n_estimators=100, contamination=0.05, random_state=42, threshold=0.0

## Results Summary

| Method | Dataset | Recall | FPR | F1 | AUC | Latency | Throughput | Nodes | Edges | RT Pairs | Anomalous |
|---|---|---|---|---|---|---|---|---|---|---|---|
| flow_only | LANL-2015 | 0.0032 | 0.0713 | 0.0002 | 0.0000 | 501.9s | 62,990/s | 11,586 | 131,562 | 35/308 | 9,380 |
| auth_only | LANL-2015 | 0.9545 | 0.0632 | 0.0222 | 0.0000 | 5,036s | 20,666/s | 90,783 | 409,100 | 302/308 | 26,120 |
| combined | LANL-2015 | 0.8701 | 0.0707 | 0.0146 | 0.0000 | 6,824s | 19,885/s | 91,589 | 512,529 | 305/308 | 36,473 |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0543 | 0.1065 | 0.6353 | 0s | 0/s | — | — | — | — |
| isolation_forest | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.4487 | 0s | 0/s | — | — | — | — |

## Sanity Checks

### 1. Flow-only is nearly useless ✓ (expected)
- Recall 0.0032 → flow data alone captures only 35/308 red team pairs
- Flow edges score via rarity_rank alone (no auth-specific signals like NTLM/Network logon)
- This is a valid baseline — confirms auth data carries the detection signal

### 2. Auth_only has best recall ✓ (makes sense)
- 95.45% recall — 302/308 red team pairs detected
- Auth events directly map to lateral movement (logon events are the attack vector)
- 6 red team pairs not in graph at all (not present in auth data within the time windows)

### 3. Combined performs worse than auth_only ✗ (problematic)
- Recall drops from 95.45% → 87.01% when adding flow data
- F1 drops from 0.0222 → 0.0146
- FPR increases from 6.32% → 7.07%
- **Why**: Adding flow edges (which score via rarity_rank only) dilutes the graph. The 103,429 additional flow edges (512K - 409K) have different scoring characteristics — their rarity-based scores shift the 90th percentile threshold upward (0.843 vs 0.7847), causing some true red team auth edges to fall below threshold
- The threshold is global (90th percentile across ALL edges), so flow noise raises the bar

### 4. F1 scores are very low across all methods ✗ (major concern)
- Best F1 = 0.0222 (auth_only) — extremely poor
- Root cause: massive class imbalance. ~308 red team pairs vs ~409K total edges
- Even with good recall, precision is killed: 302 true positives / 26,120 anomalous = ~1.2% precision
- The 90th percentile threshold is too low — flags 26K+ edges as anomalous when only ~300 are real

### 5. IsolationForest is completely broken ✗
- Recall=1.0, FPR=1.0 → flags everything as anomalous
- AUC=0.4487 (below random = 0.5)
- **Why**: threshold=0.0 combined with `score_samples()` returns negative values for anomalies — but the decision boundary at 0.0 classifies everything as anomalous. The contamination=0.05 is being ignored because threshold is hardcoded to 0.0

### 6. OneClassSVM is weak but at least functional
- AUC=0.6353 (barely above random)
- F1=0.1065 — best F1 in the entire experiment (still poor)
- Recall=0.1612 — misses 84% of lateral movement
- nu=0.05 may be too low for this dataset

### 7. AUC=0.0 for all LANL methods ✗
- AUC is hardcoded to 0.0 in the streaming pipeline (line 317: `"auc": 0.0`)
- No proper ROC curve computed — only single (FPR, recall) point
- This is a code issue, not a result issue — the single-point ROC approximation in visualization is misleading

### 8. Path enumeration is expensive but underutilized
- 94M+ paths enumerated for auth_only, 110M+ for combined
- Only top 50 returned — the rest discarded
- Path scoring doesn't feed back into edge detection (detection is purely edge-level)
- 12-20 minutes spent on path enumeration that doesn't affect results

### 9. Time windows are massive
- 749 red team events → 25 merged windows with ±3600s half-windows
- Merged windows likely span most of the dataset's time range
- This means almost all 104M auth events and 31M flow events are included
- Smaller windows would be more realistic for real-time detection

### 10. Betweenness centrality skipped for large graphs
- Only computed when nodes ≤ 5000 (features.py line 73)
- All three methods exceed this: 11K, 90K, 91K nodes
- Feature exists but is always 0.0 — wasted column

## Parameter Tuning Recommendations

### High Priority

#### 1. Fix the detection threshold (critical)
- **Current**: 90th percentile → flags ~10% of all edges
- **Problem**: With 308 red team pairs among ~400K edges, even 1% FPR = ~4K false positives
- **Try**: 99th or 99.5th percentile → dramatically fewer false positives
- **Alternative**: Use a cost-sensitive threshold that optimizes F1 directly (search over percentiles)
- **Expected impact**: F1 could improve 5-10x

#### 2. Fix IsolationForest baseline
- **Current**: `threshold=0.0` in `_evaluate()` → everything flagged
- **Fix**: Use the model's built-in `.predict()` method instead of manual thresholding, or set `contamination` to match actual anomaly rate in the dataset
- **Code**: `dapt_baselines.py` line 92 — `threshold=0.0` should use `model.offset_` (IsolationForest's decision boundary)

#### 3. Make combined method additive, not dilutive
- **Current**: Flow edges use rarity_rank only, which shifts the global threshold upward
- **Fix A**: Score flow edges with their own feature weights (e.g., include protocol rarity, unusual ports, packet/byte anomalies)
- **Fix B**: Use per-method thresholds instead of a single global 90th percentile
- **Fix C**: Weight auth edges higher in combined scoring (e.g., 2x multiplier)
- **Expected impact**: Combined recall should match or exceed auth_only

#### 4. Compute actual AUC for LANL methods
- **Current**: Hardcoded 0.0
- **Fix**: Store per-edge scores and labels, compute `roc_auc_score`
- **Expected impact**: Enables proper ROC analysis and threshold selection

### Medium Priority

#### 5. Reduce window size
- **Current**: ±3600s (2-hour windows around each red team event)
- **Try**: ±300s (5 min) or ±600s (10 min)
- **Why**: Smaller windows create sparser graphs, faster processing, and more realistic real-time detection
- **Risk**: May miss red team pairs that occur outside tight windows

#### 6. Increase max path hops selectively
- **Current**: 4 hops (generates 94M+ paths)
- **Try**: 3 hops to reduce computation, or keep 4 but increase top_k from 50 to 200
- **Consider**: Use path scores as features for edge detection rather than reporting top-50 only
- **Path enumeration takes 12-20 min but doesn't affect detection results** — either use it or skip it

#### 7. Add flow-specific edge features
- **Current**: Flow edges scored by rarity alone
- **Add**: unusual port flags (high ports > 49152), protocol rarity, byte/packet ratio anomalies, duration outliers
- **This would give flow edges meaningful anomaly signals** similar to auth's NTLM/Network logon

#### 8. Tune OneClassSVM
- **Current**: nu=0.05, gamma="scale"
- **Try**: nu=0.1 or 0.15 (allow more anomalies in training), kernel="poly" or tune gamma
- **Cross-validate** nu on a held-out portion

#### 9. Enable betweenness for smaller subgraphs
- **Current**: Skipped for >5000 nodes
- **Alternative**: Compute approximate betweenness (`igraph.Graph.betweenness` with cutoff parameter) or compute on the largest connected component only

### Low Priority / Future Work

#### 10. Temporal decay for edge scoring
- Edges from the full time range weighted equally
- Add exponential time decay: recent events score higher

#### 11. Adaptive threshold per time window
- Single global threshold applied to all edges across all time
- Per-window thresholds would adapt to local traffic density

#### 12. Graph-level anomaly detection
- Current detection is edge-level only
- Use path scores or subgraph patterns (e.g., star-shaped fan-out) as additional signals

#### 13. Add more baselines
- Kitsune (autoencoder ensemble) from related work
- Graph neural network (e.g., GCN-based anomaly detector)
- Euler's temporal link prediction approach

## Key Takeaways

1. **Auth data is the primary signal** — flow data currently hurts more than it helps
2. **The 90th percentile threshold is too permissive** — this is the single biggest lever for improvement
3. **IsolationForest baseline is broken** — must fix before including in any report
4. **F1 ≈ 0.02 is not usable** — needs at minimum 10x improvement to be practical
5. **Path scoring is expensive and unused** — either integrate it into detection or remove the overhead
6. **The combined method should theoretically be superior** — the issue is in how flow edges are scored/thresholded, not in the graph approach itself
