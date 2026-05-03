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

# New Analysis After Changes Made

## Run Metadata

- **Run ID**: `20260502_165755`
- **Total wall time**: ~4h12m (09:57:55 → 14:10:01)
- **Command**: `make pipeline` → `uv run python run_experiment.py` (all defaults, post-fix config)
- **Results dir**: `results/20260502_165755/`
- **Changes since last run**: commit `49e0c60` — auto-optimize threshold, real AUC, flow edge features, auth weight multiplier, path boost, IsolationForest/SVM threshold fixes

## Parameters Used

### Pipeline Config (`pipeline_config.json`)

| Section | Parameter | Value | Changed from previous? |
|---|---|---|---|
| scoring | `threshold_mode` | `auto_optimize` | was fixed 90th percentile |
| scoring | `threshold_search_range` | [90,95,97,99,99.5,99.9] | new |
| scoring | `flow_weights` | {rarity: 0.4, unusual_port: 0.3, protocol_rarity: 0.3} | was rarity only |
| scoring | `auth_weight_multiplier` | 1.5 | was 1.0 (no multiplier) |
| scoring | `path_boost_factor` | 0.1 | was 0 (no boost) |
| scoring | `temporal_decay_rate` | 0.0 | new (not active) |
| features | `approximate_betweenness` | true | was skipped entirely |
| features | `betweenness_cutoff` | 3 | new |
| baselines | `oneclass_svm.nu` | 0.1 | was 0.05 |
| baselines | `isolation_forest` | uses `model.offset_` | was hardcoded 0.0 |

### New Edge Features (flow edges)

- `is_unusual_dst_port` — flags ports {22,23,445,3389,5985,5986} or >49152
- `protocol_rarity` — `1 - (protocol_count / total_flow_edges)`
- `byte_per_packet` — percentile rank of byte_count/pkt_count
- `duration_zscore` — z-score of duration across all edges
- `temporal_decay_weight` — exponential decay (rate=0.0, effectively inactive)

## Results Summary

| Method | Dataset | Recall | FPR | F1 | AUC | Threshold | Pctl | Anomalous | Latency |
|---|---|---|---|---|---|---|---|---|---|
| flow_only | LANL-2015 | 0.0130 | 0.0297 | 0.0019 | 0.5785 | 0.691 | 97th | 3,907 | 585s |
| auth_only | LANL-2015 | 0.7468 | 0.0296 | 0.0364 | 0.9508 | 1.401 | 95th | 12,319 | 6,142s |
| combined | LANL-2015 | 0.6623 | 0.0196 | 0.0387 | 0.9544 | 1.407 | 97th | 10,243 | 7,598s |
| oneclass_svm | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.6463 | — | — | — | — |
| isolation_forest | DAPT2020 | 0.0069 | 0.0500 | 0.0051 | 0.4487 | — | — | — | — |

### Old vs New Comparison

| Method | Metric | Old | New | Change |
|---|---|---|---|---|
| flow_only | Recall | 0.0032 | 0.0130 | +306% |
| flow_only | FPR | 0.0713 | 0.0297 | -58% |
| flow_only | F1 | 0.0002 | 0.0019 | +850% |
| flow_only | AUC | 0.0000 | 0.5785 | ✓ computed |
| auth_only | Recall | 0.9545 | 0.7468 | -22% |
| auth_only | FPR | 0.0632 | 0.0296 | -53% |
| auth_only | F1 | 0.0222 | 0.0364 | +64% |
| auth_only | AUC | 0.0000 | 0.9508 | ✓ computed |
| combined | Recall | 0.8701 | 0.6623 | -24% |
| combined | FPR | 0.0707 | 0.0196 | -72% |
| combined | F1 | 0.0146 | 0.0387 | +165% |
| combined | AUC | 0.0000 | 0.9544 | ✓ computed |
| oneclass_svm | Recall | 0.1612 | 1.0000 | **broken** |
| oneclass_svm | FPR | 0.0543 | 1.0000 | **broken** |
| oneclass_svm | F1 | 0.1065 | 0.0550 | -48% |
| isolation_forest | Recall | 1.0000 | 0.0069 | fixed (was broken) |
| isolation_forest | FPR | 1.0000 | 0.0500 | fixed (was broken) |
| isolation_forest | F1 | 0.0550 | 0.0051 | -91% |

## Sanity Checks

### 1. Auto-optimize threshold works ✓

- flow_only: chose 97th percentile (threshold=0.691)
- auth_only: chose 95th percentile (threshold=1.401)
- combined: chose 97th percentile (threshold=1.407)
- All three chose higher percentiles than the previous fixed 90th, confirming 90th was too permissive
- F1 improved 64-165% across all LANL methods

### 2. AUC now properly computed ✓

- auth_only: 0.9508 — excellent discrimination
- combined: 0.9544 — marginally better than auth_only
- flow_only: 0.5785 — barely above random (0.5), confirming flow data alone is weak

### 3. FPR dramatically improved ✓

- combined: 7.07% → 1.96% (3.6x better)
- auth_only: 6.32% → 2.96% (2.1x better)
- False positives roughly halved across the board

### 4. Combined method now beats auth_only on F1 ✓ (improvement from previous)

- combined F1 = 0.0387 > auth_only F1 = 0.0364
- Previous run: combined (0.0146) was worse than auth_only (0.0222)
- **Why**: auth_weight_multiplier=1.5 pushes auth edges higher in combined graph, flow weights give meaningful scores, and 97th percentile threshold is tighter
- Combined also has lower FPR (1.96% vs 2.96%) and higher AUC (0.9544 vs 0.9508)

### 5. Recall dropped — precision/recall tradeoff ⚠

- auth_only: 95.45% → 74.68% (302→225 red team pairs detected)
- combined: 87.01% → 66.23% (305→202 red team pairs detected)
- This is the expected cost of higher thresholds: fewer false positives but also fewer true positives
- ~75 red team pairs lost in auth_only, ~103 lost in combined

### 6. OneClassSVM is now broken ✗ (regression)

- Previous: recall=0.1612, fpr=0.0543 (weak but functional)
- Now: recall=1.0, fpr=1.0 (flags everything)
- **Why**: Changing nu from 0.05→0.1 made the model more permissive. Combined with the `model.offset_` threshold fix, the decision boundary shifted. For OneClassSVM, `offset_` may be negative, so `score >= offset_` is always true for training data
- **Fix needed**: The offset_ approach works differently for SVM vs IF. Need to use `model.predict()` or compute a proper percentile threshold on decision scores

### 7. IsolationForest fixed but overcorrected ⚠

- Previous: recall=1.0, fpr=1.0 (flagged everything)
- Now: recall=0.0069, fpr=0.05 (detects almost nothing)
- `model.offset_` is likely very negative, making `score >= offset_` almost never true
- AUC unchanged at 0.4487 (still below random) — model itself isn't learning useful patterns
- **Fix needed**: Use `model.predict()` which uses the built-in contamination-based threshold

### 8. Path boost applied but minimal impact ⚠

- Path boost factor=0.1 applied to all three LANL methods
- Max path scores: 0.7848 (flow), 1.4772 (auth), 1.479 (combined)
- Boost is additive to edge scores — 10% of path score added
- Given path scores are similar to edge scores, the boost is ~0.01-0.15 range
- Path enumeration still takes significant time (part of the 10-47 min scoring)

### 9. Approximate betweenness computed ✓

- cutoff=3 used for graphs >5000 nodes
- Betweenness no longer always 0
- But impact on scoring is unclear (betweenness is a node feature, not directly used in edge scoring)

### 10. Flow edges now have meaningful features ✓

- 3-feature scoring: rarity (0.4) + unusual_port (0.3) + protocol_rarity (0.3)
- Flow AUC: 0.5785 — slightly above random but still weak
- Flow recall improved from 0.0032→0.0130 (4x) but remains very low
- 35 red team pairs in flow graph, only 4 detected

## Parameter Tuning Recommendations

### High Priority

#### 1. Fix OneClassSVM baseline (regression)

- **Current**: `model.offset_` threshold flags everything
- **Fix**: Use `model.predict(X)` which returns {-1, 1} using the internal contamination-based decision boundary
- **Or**: Use `model.decision_function(X)` and set threshold at `np.percentile(scores, 100 * contamination)`

#### 2. Fix IsolationForest threshold (overcorrection)

- **Current**: `model.offset_` too strict, detects almost nothing
- **Fix**: Same as SVM — use `model.predict(X)` or `model.decision_function(X)` with proper percentile
- **AUC=0.4487** suggests the model itself may not be learning useful patterns regardless of threshold

#### 3. Recover recall without sacrificing F1

- **Current tradeoff**: F1 improved 1.6-2.7x but recall dropped 22-24%
- **Approach A**: Use F2 or F0.5 score for threshold optimization instead of F1 (F2 weights recall more)
- **Approach B**: Two-stage detection — high recall first pass, then filter by additional features
- **Approach C**: Per-edge-type thresholds (separate for auth vs flow in combined)

### Medium Priority

#### 4. Increase path boost factor

- **Current**: 0.1 — very conservative
- **Try**: 0.3 or 0.5 to give path information more weight
- Path scores are meaningful (max=1.479) but diluted by 10% factor

#### 5. Activate temporal decay

- **Current**: `temporal_decay_rate=0.0` (inactive)
- **Try**: rate=1.0 or 2.0 — recent events should score higher
- The feature code is in place, just needs config change

#### 6. Tune flow edge features

- `is_unusual_dst_port` may be too aggressive — flags all high ports (>49152)
- `protocol_rarity` heavily weights rare protocols but rare ≠ malicious
- Consider byte/packet ratio anomalies and duration outliers more heavily

### Low Priority / Future Work

#### 7. Feature importance analysis

- 5 new flow features added but unclear which help
- Run ablation: score with each feature individually to measure contribution
- AUC=0.5785 suggests the new features help marginally at best

#### 8. Ensemble the LANL methods

- auth_only has highest recall (0.7468), combined has best F1 (0.0387) and AUC (0.9544)
- Union of detections would improve recall; intersection would improve precision
- Simple voting ensemble across methods could outperform any single method

## Key Takeaways (Updated)

1. **Auto-optimize threshold was the biggest win** — F1 improved 64-165%, FPR halved
2. **Combined method now outperforms auth_only on F1 and AUC** — flow data helps when properly weighted
3. **AUC=0.95+ confirms graph-based approach has strong discriminative power** — the signal was always there, threshold was hiding it
4. **Recall drop (22-24%) is the cost** — 75-103 more red team pairs missed
5. **OneClassSVM regressed** — nu=0.1 + offset_ fix broke it (flags everything)
6. **IsolationForest overcorrected** — now detects almost nothing
7. **F1 still only ~0.04** — improved but still impractical; class imbalance (308/400K) is the ceiling
8. **Path boost has minimal impact at factor=0.1** — either increase or remove the overhead
