# Pipeline Differences: `feat/gradient-descent-draft` vs `main`

## main branch

```
main.py
  │
  ├── Load config (pipeline_config.json)
  │
  ├── Parse CLI: --data-dir, --window-size, --dapt-dir, --sample
  │
  ├─────────────────────────────────────────────────────────────
  │  METHOD 1: flow_only
  │    stream flows.txt.gz → graph (flows only)
  │    extract features
  │    score edges:
  │      flow_weights = {edge_rarity: 0.4, is_unusual_dst_port: 0.3, protocol_rarity: 0.3}
  │    threshold sweep → metrics
  │
  ├─────────────────────────────────────────────────────────────
  │  METHOD 2: auth_only
  │    stream auth.txt.gz → graph (auth only)
  │    extract features
  │    score edges:
  │      auth_weights = {is_ntlm: 0.4, is_network_logon: 0.3, edge_rarity: 0.3}
  │      × auth_weight_multiplier = 1.5
  │    threshold sweep → metrics
  │
  ├─────────────────────────────────────────────────────────────
  │  METHOD 3: combined
  │    stream auth.txt.gz + flows.txt.gz → unified graph
  │    extract features
  │    score edges:
  │      auth edges → auth_weights × 1.5
  │      flow edges → flow_weights
  │      temporal decay post-hoc
  │    threshold sweep → metrics
  │
  ├─────────────────────────────────────────────────────────────
  │  BASELINES (on LANL combined edge features)
  │    OneClass SVM  → metrics
  │    Isolation Forest → metrics
  │
  ├─────────────────────────────────────────────────────────────
  │  DAPT2020 dataset
  │    load DAPT2020 CSVs
  │    graph-based detection → metrics
  │
  └─────────────────────────────────────────────────────────────
     → Multi-method comparison table (up to 6 methods)
     → Reporting + Visualization
```

## this branch (feat/gradient-descent-draft)

```
main.py
  │
  ├── Load config (pipeline_config.json)
  │
  ├── Parse CLI: --sample only
  │
  ├─────────────────────────────────────────────────────────────
  │  COMBINED (only method, only LANL-2015)
  │
  │    stream auth.txt.gz + flows.txt.gz → unified graph
  │       ↓
  │    extract edge features (16) + node features (9) + graph features (5)
  │       ↓
  │    WEIGHT OPTIMIZATION (new)
  │      features: is_ntlm, source_fan_out, dst_in_degree,
  │                is_network_logon, dst_fan_out_ratio
  │      labels: red-team ground truth on valid edges
  │      Nelder-Mead → maximize AUC (up to 500 iterations)
  │      fallback: equal weights (0.2 each)
  │       ↓
  │    score edges:
  │      unified weight vector (from optimizer) × features
  │      zero out self-loops + user edges
  │      rank-transform edge_rarity, protocol_rarity
  │       ↓
  │    enumerate paths (BFS, top-10 outgoing/node, top-50 paths)
  │       ↓
  │    boost edges from paths: score += 0.1 × path_score
  │       ↓
  │    graph-level scoring
  │       ↓
  │    threshold sweep [90, 95, 97, 99, 99.5, 99.9] → pick best F1
  │       ↓
  │    compute metrics: recall, FPR, F1, precision, AUC
  │
  └─────────────────────────────────────────────────────────────
     → Single result row
     → Reporting + Visualization
```

## Key Differences

### Datasets

| | main | this branch |
|--|------|-------------|
| LANL-2015 | ✅ | ✅ only dataset |
| DAPT2020 | ✅ | ❌ |

### Methods

| | main | this branch |
|--|------|-------------|
| flow_only | ✅ | ❌ |
| auth_only | ✅ | ❌ |
| combined | ✅ | ✅ (only method) |
| OneClass SVM | ✅ | ❌ |
| Isolation Forest | ✅ | ❌ |
| DAPT graph | ✅ | ❌ |

### Weights

**main**: hardcoded per edge type:
- Auth: `{is_ntlm: 0.4, is_network_logon: 0.3, edge_rarity: 0.3}` × 1.5 multiplier
- Flow: `{edge_rarity: 0.4, is_unusual_dst_port: 0.3, protocol_rarity: 0.3}`

**this branch**: Nelder-Mead optimizer maximizes AUC over 5 features at runtime, fallback equal weights. Same weights for all edges regardless of type.

### Edge Scoring

**main**: split logic — auth edges and flow edges scored with different weight sets and multipliers.

**this branch**: unified — all edges scored with same optimized weight vector. Path-based boost added (`score += 0.1 × path_score`).

### Threshold

Same on both: percentile sweep maximizing F1.

### Output

**main**: comparison across up to 6 methods. **this branch**: single result.
