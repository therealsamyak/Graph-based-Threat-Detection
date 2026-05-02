# Pipeline Bug Fixes + Performance Optimization

## TL;DR

> **Fix 12 bugs (4 critical, 3 high) + optimize parallelism across scorer, features, data_loader. Remove dead code. Ensure pipeline runs end-to-end without errors.**
>
> **Deliverables**:
> - Bug-free streaming pipeline (streaming_pipeline.py, scorer.py, features.py, data_loader.py)
> - Correct DAPT baselines (dapt_baselines.py)
> - Correct metrics computation (FPR, precision, recall all in pair-space)
> - Optimized ProcessPoolExecutor path enumeration (no igraph pickling)
> - Single-pass auth_failure + port_diversity computation
> - O(log n) window membership via bisect
> - Dead code removed (evaluate.py, graph_builder.py, single_source.py, main.py)
>
> **Estimated Effort**: Large
> **Parallel Execution**: YES - 4 waves
> **Critical Path**: T1 → T4 → T5 → T8 → T9 → T10 → T11 → F1-F4

---

## Context

### Original Request
User wants pipeline fully debugged and optimized with maximum multiprocessing before a production run. Recent optimization commits (ProcessPoolExecutor in scorer.py, timestamped results dirs) introduced potential issues.

### Interview Summary
- Oracle found 15 bugs total (4 CRITICAL, 3 HIGH, 4 MEDIUM, 4 LOW)
- Metis confirmed all bugs + identified ProcessPoolExecutor igraph pickling as fragile
- Librarian confirmed igraph pickle works but memory-heavy
- User wants maximum Python multiprocessing parallelism

### Key Bug Summary

| # | Severity | File | Bug | Impact |
|---|----------|------|-----|--------|
| 1 | CRITICAL | dapt_baselines.py:47 | Binary predictions to roc_auc_score | Degenerate AUC |
| 2 | CRITICAL | streaming_pipeline.py:56 | `_add_edge` overwrites time on dupes | Loses temporal info |
| 3 | CRITICAL | streaming_pipeline.py:282-283 | FPR/precision dimension mismatch (edges vs pairs) | Wrong metrics |
| 4 | CRITICAL | streaming_pipeline.py:60-81 | No user-user auth edges | Incomplete graph |
| 5 | HIGH | features.py:104 | Edge rarity always 1.0 (deduped edges, pair_count=1) | Useless feature |
| 6 | HIGH | scorer.py:85-134 | auth_failure+port_diversity are source-level, not edge-level | All edges from same src identical score |
| 7 | HIGH | scorer.py:211 | ProcessPoolExecutor pickles entire igraph | Memory-heavy, fragile |
| 8 | MEDIUM | features.py:124 | transitivity_local_undirected on directed graph | Semantically wrong |
| 9 | MEDIUM | data_loader.py:73-79 | O(n) linear scan for window membership | Slow for many windows |
| 10 | MEDIUM | run_experiment.py:142-143 | Red team loaded twice | Wasted I/O |
| 11 | MEDIUM | streaming_pipeline.py:164 | Return type annotation says 2-tuple, returns 3 | Misleading |
| 12 | LOW | run_experiment.py:80-81 | Dead variables (run_id, results_base) | Cosmetic |

### Metis Review
**Identified Gaps** (all addressed):
- ProcessPoolExecutor igraph pickling → refactor to adjacency dict + numpy arrays
- Edge rarity uses pair_count (always 1 due to dedup) → use weight attribute
- Source-level scoring → make edge-level where possible
- Missing user-user auth edges → add to feed_auth_event
- Dead code → delete entirely

---

## Work Objectives

### Core Objective
Fix all correctness bugs, maximize parallelism, remove dead code. Pipeline must produce correct metrics end-to-end.

### Concrete Deliverables
- streaming_pipeline.py: Fixed edge dedup, user-user edges, correct metrics, return annotation
- scorer.py: Refactored parallel path enum (no igraph pickle), single-pass auth+port, edge-level scoring
- features.py: Fixed edge rarity (use weight), fixed clustering, precomputed degrees
- data_loader.py: bisect for window membership
- dapt_baselines.py: Continuous scores for AUC
- run_experiment.py: Remove dead vars, fix double red-team load
- Deleted: evaluate.py, graph_builder.py, baselines/single_source.py, main.py

### Definition of Done
- [ ] `uv run python run_experiment.py --data-dir data/LANL-Dataset-2015 --dapt-dir data/DAPT2020` completes with exit code 0
- [ ] All metrics (recall, FPR, F1, AUC) are non-zero and non-degenerate
- [ ] DAPT AUC is between 0.3 and 0.99 (not exactly 0.5)
- [ ] No import errors after file deletions

### Must Have
- All 12 bugs fixed
- ProcessPoolExecutor path enumeration works without igraph pickling
- Metrics computed consistently in pair-space
- User-user auth edges in graph
- Edge rarity uses event count (weight), not pair_count

### Must NOT Have (Guardrails)
- No new features, detection methods, or architectural changes
- No changes to output CSV/JSON formats
- No modifications to visualize.py or generate_comparison.py
- No changes to DAPT data loader (dapt_loader.py)
- No parallelization of the method loop (flow_only/auth_only/combined) — same gz files
- No TDD — verify via pipeline run only
- No touching combined graph edge dedup key scheme beyond adding edge_type

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** - ALL verification is agent-executed.

### Test Decision
- **Infrastructure exists**: NO
- **Automated tests**: None
- **Framework**: none
- **Verification**: Full pipeline run + targeted python -c assertions

### QA Policy
Every task includes agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **Pipeline smoke test**: `uv run python run_experiment.py` - full run, exit code 0
- **Targeted assertions**: `uv run python -c "..."` for specific bug fixes
- **Metric validation**: Check output CSVs for non-degenerate values

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Foundation - cleanup + dead code):
├── T1: Delete dead files [quick]
├── T2: Fix return type annotation + dead vars [quick]
└── T3: Fix _time_in_any_window with bisect [quick]

Wave 2 (Critical bug fixes - correctness):
├── T4: Fix _add_edge time overwrite + user-user auth edges [unspecified-high]
├── T5: Fix FPR/precision/recall in pair-space [unspecified-high]
├── T6: Fix DAPT baselines - continuous scores [unspecified-high]
└── T7: Fix edge rarity to use weight [unspecified-high]

Wave 3 (Performance - optimization + parallelism):
├── T8: Refactor scorer - adjacency dict + numpy, no igraph pickle [deep]
├── T9: Merge auth_failure + port_diversity into single pass [unspecified-high]
├── T10: Precompute degree arrays in features.py [quick]
└── T11: Fix clustering on directed graph [quick]

Wave 4 (Integration):
├── T12: Fix double red-team load in run_experiment.py [quick]
├── T13: Handle degenerate threshold case [quick]
└── T14: Full pipeline smoke test [deep]

Wave FINAL (After ALL tasks — 4 parallel reviews):
├── F1: Plan compliance audit (oracle)
├── F2: Code quality review (unspecified-high)
├── F3: Real manual QA (unspecified-high)
└── F4: Scope fidelity check (deep)
→ Present results → Get explicit user okay

Critical Path: T1 → T4 → T5 → T8 → T14 → F1-F4
Max Concurrent: 4 (Wave 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| T1 | - | T4, T6 | 1 |
| T2 | - | - | 1 |
| T3 | - | - | 1 |
| T4 | T1 | T5, T8 | 2 |
| T5 | T4 | T14 | 2 |
| T6 | T1 | T14 | 2 |
| T7 | T4 | T14 | 2 |
| T8 | T4 | T14 | 3 |
| T9 | T7 | T14 | 3 |
| T10 | - | - | 3 |
| T11 | - | - | 3 |
| T12 | - | - | 4 |
| T13 | T5 | T14 | 4 |
| T14 | T5,T6,T7,T8,T9,T12,T13 | F1-F4 | 4 |
| F1-F4 | T14 | user okay | FINAL |

### Agent Dispatch Summary

- **Wave 1**: 3 tasks - T1 → `quick`, T2 → `quick`, T3 → `quick`
- **Wave 2**: 4 tasks - T4 → `unspecified-high`, T5 → `unspecified-high`, T6 → `unspecified-high`, T7 → `unspecified-high`
- **Wave 3**: 4 tasks - T8 → `deep`, T9 → `unspecified-high`, T10 → `quick`, T11 → `quick`
- **Wave 4**: 3 tasks - T12 → `quick`, T13 → `quick`, T14 → `deep`
- **FINAL**: 4 tasks - F1 → `oracle`, F2 → `unspecified-high`, F3 → `unspecified-high`, F4 → `deep`

---

## TODOs

- [x] 1. Delete dead code files

  **What to do**:
  - Delete `src/evaluate.py` — entirely unused (no imports anywhere)
  - Delete `src/graph_builder.py` — only imported by single_source.py (also dead)
  - Delete `src/baselines/single_source.py` — no imports found
  - Delete `main.py` — hello world stub, never called
  - Verify no import chain references these files: `grep -r "from src.evaluate\|from src.graph_builder\|from src.baselines.single_source\|import main" src/ run_experiment.py`

  **Must NOT do**:
  - Do NOT delete `src/baselines/dapt_loader.py` or `src/baselines/dapt_baselines.py` (active)
  - Do NOT delete `src/data_loader.py` (active)
  - Do NOT delete `src/visualize.py` or `src/generate_comparison.py`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T2, T3)
  - **Blocks**: T4, T6
  - **Blocked By**: None

  **References**:
  - `src/evaluate.py` — dead, verify with grep
  - `src/graph_builder.py` — dead, verify with grep
  - `src/baselines/single_source.py` — dead, verify with grep
  - `main.py` — dead stub

  **Acceptance Criteria**:
  - [ ] All 4 files deleted
  - [ ] `uv run python -c "from src.streaming_pipeline import run_streaming_experiment; from src.baselines.dapt_baselines import run_dapt_baselines"` succeeds
  - [ ] No grep matches for deleted module imports

  **QA Scenarios**:
  ```
  Scenario: Dead files removed without breaking imports
    Tool: Bash
    Steps:
      1. test ! -f src/evaluate.py && test ! -f src/graph_builder.py && test ! -f src/baselines/single_source.py && test ! -f main.py
      2. uv run python -c "from src.streaming_pipeline import run_streaming_experiment; from src.baselines.dapt_baselines import run_dapt_baselines"
    Expected Result: Both commands exit 0
    Evidence: .sisyphus/evidence/task-1-dead-code-removed.txt
  ```

  **Commit**: YES
  - Message: `cleanup: remove dead code (evaluate.py, graph_builder.py, single_source.py, main.py)`
  - Files: `src/evaluate.py, src/graph_builder.py, src/baselines/single_source.py, main.py`

- [x] 2. Fix return type annotation + remove dead variables

  **What to do**:
  - `streaming_pipeline.py:164`: Change return type from `tuple[list[dict], dict]` to `tuple[list[dict], dict, str]`
  - `streaming_pipeline.py:171-174`: Update docstring to mention 3rd return value (results_base path)
  - `run_experiment.py:80-81`: Remove dead `run_id` and `results_base` variables (lines 80-81). The values are overwritten by the 3-tuple return on line 87.
  - `run_experiment.py:79`: Remove `from datetime import datetime, timezone` import if no longer used after removing dead vars (check — it IS used on line 75-76 import in streaming_pipeline.py but NOT in run_experiment.py after line 80 removal)

  **Must NOT do**:
  - Do NOT change the actual return value or logic

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T3)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/streaming_pipeline.py:164` — return type annotation
  - `src/streaming_pipeline.py:385` — actual return: `return all_results, viz_data, str(results_base)`
  - `run_experiment.py:75-81` — dead datetime import + variables
  - `run_experiment.py:87` — `lanl_results, viz_data, results_base = run_streaming_experiment(...)`

  **Acceptance Criteria**:
  - [ ] `streaming_pipeline.py` return annotation matches 3-tuple
  - [ ] `run_experiment.py` has no dead datetime import or variables
  - [ ] `uv run python -c "from src.streaming_pipeline import run_streaming_experiment"` succeeds

  **QA Scenarios**:
  ```
  Scenario: Return annotation matches implementation
    Tool: Bash
    Steps:
      1. grep -n "tuple\[list\[dict\], dict, str\]" src/streaming_pipeline.py
      2. grep -c "from datetime" run_experiment.py
    Expected Result: Annotation found on line ~164, 0 datetime imports in run_experiment.py
    Evidence: .sisyphus/evidence/task-2-type-annotation.txt
  ```

  **Commit**: YES
  - Message: `fix(pipeline): correct return type annotation + remove dead vars`
  - Files: `src/streaming_pipeline.py, run_experiment.py`

- [x] 3. Fix _time_in_any_window with bisect

  **What to do**:
  - `src/data_loader.py:73-79`: Replace linear scan with `bisect` for O(log n) lookup
  - Import `bisect` at top of file
  - Implementation: extract window starts into a separate list, use `bisect_left` to find candidate window, check if time falls within it
  - Windows are already sorted (from `_build_window_intervals`), so no sorting needed
  - New implementation:
    ```python
    def _time_in_any_window(time: int, windows: list[tuple[int, int]]) -> bool:
        starts = [w[0] for w in windows]
        i = bisect.bisect_right(starts, time) - 1
        if i >= 0 and windows[i][0] <= time <= windows[i][1]:
            return True
        return False
    ```
  - Note: Since windows are non-overlapping (merged in `_build_window_intervals`), `bisect_right` on starts gives the right index. Check one window only.

  **Must NOT do**:
  - Do NOT modify `_build_window_intervals` (it already produces sorted merged windows)
  - Do NOT change the function signature

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 1 (with T1, T2)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/data_loader.py:73-79` — current O(n) implementation
  - `src/data_loader.py:54-70` — `_build_window_intervals` produces sorted, merged windows (non-overlapping)

  **Acceptance Criteria**:
  - [ ] `bisect` imported in data_loader.py
  - [ ] Function signature unchanged
  - [ ] `uv run python -c "from src.data_loader import _time_in_any_window; assert _time_in_any_window(5, [(1,10), (20,30)]) == True; assert _time_in_any_window(15, [(1,10), (20,30)]) == False; assert _time_in_any_window(25, [(1,10), (20,30)]) == True"` passes

  **QA Scenarios**:
  ```
  Scenario: Bisect returns same results as linear scan
    Tool: Bash
    Steps:
      1. uv run python -c "
from src.data_loader import _time_in_any_window
windows = [(1,10), (20,30), (50,60), (100,200)]
# Test all cases: in window, between windows, before first, after last
assert _time_in_any_window(5, windows) == True
assert _time_in_any_window(15, windows) == False
assert _time_in_any_window(25, windows) == True
assert _time_in_any_window(55, windows) == True
assert _time_in_any_window(150, windows) == True
assert _time_in_any_window(0, windows) == False
assert _time_in_any_window(201, windows) == False
assert _time_in_any_window(10, windows) == True  # boundary
assert _time_in_any_window(20, windows) == True  # boundary
print('All bisect tests passed')
"
    Expected Result: All assertions pass
    Evidence: .sisyphus/evidence/task-3-bisect-correctness.txt
  ```

  **Commit**: YES
  - Message: `perf(loader): use bisect for O(log n) window membership`
  - Files: `src/data_loader.py`

- [x] 4. Fix _add_edge time overwrite + add user-user auth edges

  **What to do**:
  - `streaming_pipeline.py:54-58` (`_add_edge`): On duplicate edge, preserve `first_time` from first occurrence AND update `last_time`:
    ```python
    def _add_edge(self, src: str, dst: str, attrs: dict) -> None:
        self._ensure_node(src, "computer")
        self._ensure_node(dst, "computer")
        key = (src, dst)
        if key in self._edge_map:
            self._edge_map[key]["weight"] += 1
            existing_time = self._edge_map[key].get("first_time", self._edge_map[key].get("time", 0))
            self._edge_map[key]["last_time"] = attrs.get("time", 0)
            self._edge_map[key]["first_time"] = existing_time
        else:
            self._edge_map[key] = {**attrs, "weight": 1, "first_time": attrs.get("time", 0)}
    ```
  - `streaming_pipeline.py:60-81` (`feed_auth_event`): Add user-user edges. After existing `_add_edge(str(src_c), str(dst_c), base)`, add:
    ```python
    if not pd.isna(src_u) and not pd.isna(dst_u):
        user_edge_attrs = {
            "type": "auth",
            "auth_type": row.get("auth_type", ""),
            "logon_type": row.get("logon_type", ""),
            "auth_orientation": row.get("auth_orientation", ""),
            "success": row.get("success", ""),
            "time": float(row.get("time", 0)),
        }
        self._add_edge(str(src_u), str(dst_u), user_edge_attrs)
    ```
  - Remove the existing `_ensure_node` calls for users (lines 78-80) since `_add_edge` already calls `_ensure_node` for src/dst. But note: `_add_edge` marks both as "computer" type — need to either: (a) make `_add_edge` accept node_type param, or (b) keep `_ensure_node` calls before `_add_edge` for user nodes. Option (b) is simpler.
  - Actually, the cleanest approach: create a `_add_edge_typed` or modify `_add_edge` to accept optional `node_type` for src/dst. Or just call `_ensure_node` for users first, then use a raw edge add. Simplest: just add a separate method or modify `_add_edge` to accept src_type/dst_type params.

  **Recommended approach**: Add `src_type` and `dst_type` params to `_add_edge` with defaults "computer":
  ```python
  def _add_edge(self, src: str, dst: str, attrs: dict, src_type: str = "computer", dst_type: str = "computer") -> None:
      self._ensure_node(src, src_type)
      self._ensure_node(dst, dst_type)
      ...
  ```
  Then in `feed_auth_event`, call: `self._add_edge(str(src_u), str(dst_u), user_edge_attrs, src_type="user", dst_type="user")`

  **Must NOT do**:
  - Do NOT change edge key from `(src,dst)` to include edge_type (would break downstream scoring)
  - Do NOT modify `feed_flow_event`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T1)
  - **Parallel Group**: Wave 2
  - **Blocks**: T5, T7, T8
  - **Blocked By**: T1

  **References**:
  - `src/streaming_pipeline.py:44-58` — `_ensure_node` and `_add_edge` current impl
  - `src/streaming_pipeline.py:60-81` — `feed_auth_event` — currently only adds computer-computer edge
  - `src/graph_builder.py` (if still exists) — reference for what non-streaming version does (may be deleted by T1)

  **Acceptance Criteria**:
  - [ ] `first_time` preserved on duplicate edges
  - [ ] `last_time` updated on duplicate edges
  - [ ] User-user auth edges added to graph
  - [ ] User nodes typed as "user", computer nodes as "computer"
  - [ ] `uv run python -c "from src.streaming_pipeline import StreamingGraphBuilder; g = StreamingGraphBuilder(); g.feed_auth_event({'src_comp':'C1','dst_comp':'C2','src_user':'U1','dst_user':'U2','auth_type':'Kerberos','logon_type':'10','auth_orientation':'LogOn','success':'1','time':100}); g.feed_auth_event({'src_comp':'C1','dst_comp':'C2','src_user':'U1','dst_user':'U2','auth_type':'Kerberos','logon_type':'10','auth_orientation':'LogOn','success':'1','time':200}); graph = g.build(); assert graph.vcount() == 4; assert graph.ecount() == 2; print('OK')"` passes (4 nodes: C1,C2,U1,U2; 2 edges: C1→C2, U1→U2)

  **QA Scenarios**:
  ```
  Scenario: Duplicate edge preserves first_time and updates last_time
    Tool: Bash
    Steps:
      1. uv run python -c "
from src.streaming_pipeline import StreamingGraphBuilder
g = StreamingGraphBuilder()
g.feed_flow_event({'src_comp':'C1','dst_comp':'C2','protocol':'6','src_port':'1234','dst_port':'80','pkt_count':10,'byte_count':100,'duration':1,'time':100})
g.feed_flow_event({'src_comp':'C1','dst_comp':'C2','protocol':'6','src_port':'5678','dst_port':'80','pkt_count':20,'byte_count':200,'duration':1,'time':200})
graph = g.build()
e = graph.es[0]
assert e['first_time'] == 100, f'first_time={e[\"first_time\"]}'
assert e['last_time'] == 200, f'last_time={e[\"last_time\"]}'
assert e['weight'] == 2, f'weight={e[\"weight\"]}'
print('Time preservation OK')
"
    Expected Result: first_time=100, last_time=200, weight=2
    Evidence: .sisyphus/evidence/task-4-time-preservation.txt

  Scenario: User-user auth edges created
    Tool: Bash
    Steps:
      1. uv run python -c "
from src.streaming_pipeline import StreamingGraphBuilder
g = StreamingGraphBuilder()
g.feed_auth_event({'src_comp':'C1','dst_comp':'C2','src_user':'U1','dst_user':'U2','auth_type':'Kerberos','logon_type':'10','auth_orientation':'LogOn','success':'1','time':100})
graph = g.build()
names = sorted([v['name'] for v in graph.vs])
assert names == ['C1','C2','U1','U2'], f'nodes={names}'
edges = [(graph.vs[e.source]['name'], graph.vs[e.target]['name']) for e in graph.es]
assert ('C1','C2') in edges, f'missing C1→C2'
assert ('U1','U2') in edges, f'missing U1→U2'
# Check node types
for v in graph.vs:
    if v['name'].startswith('U'):
        assert v['node_type'] == 'user', f'{v[\"name\"]} type={v[\"node_type\"]}'
    else:
        assert v['node_type'] == 'computer', f'{v[\"name\"]} type={v[\"node_type\"]}'
print('User-user edges OK')
"
    Expected Result: 4 nodes, 2 edges (C1→C2, U1→U2), correct node types
    Evidence: .sisyphus/evidence/task-4-user-edges.txt
  ```

  **Commit**: YES
  - Message: `fix(pipeline): preserve first_time on duplicate edges + add user-user auth edges`
  - Files: `src/streaming_pipeline.py`

- [x] 5. Fix FPR/precision/recall in consistent pair-space

  **What to do**:
  - `streaming_pipeline.py:269-284`: Rewrite metric computation to be consistent in pair-space
  - Current problem: `anomalous_edge_count` and `red_edge_count` are in edge-space, but `detected_pairs` is in pair-space. Mixing gives wrong FPR/precision.
  - New approach — everything in pair-space:
    ```python
    # Extract all anomalous pairs from anomalous paths
    anomalous_pairs: set[tuple[str, str]] = set()
    if len(anomalous_paths) > 0:
        for _, row in anomalous_paths.iterrows():
            nodes = row["path_nodes"]
            for i in range(len(nodes) - 1):
                anomalous_pairs.add((nodes[i], nodes[i + 1]))

    # All graph edges as pairs
    graph_pairs = graph_edges  # already computed on line 243-245

    # Red team pairs in this graph
    red_in_graph = rt_in_graph  # already computed on line 246

    # Metrics in pair-space
    detected_pairs = anomalous_pairs & red_in_graph
    recall = len(detected_pairs) / len(red_pairs) if red_pairs else 0.0
    true_negatives = len(graph_pairs - anomalous_pairs - red_in_graph)
    false_positives = len(anomalous_pairs - red_in_graph)
    fpr = false_positives / max(false_positives + true_negatives, 1)
    precision = len(detected_pairs) / max(len(anomalous_pairs), 1)
    f1 = 2 * recall * precision / (recall + precision) if (recall + precision) > 0 else 0.0
    ```
  - Update result dict: replace `anomalous_edges` with `anomalous_pairs`, replace `rt_pairs_in_graph` count

  **Must NOT do**:
  - Do NOT change the detection logic (threshold, path scoring)
  - Do NOT change the result dict structure (keep same keys for backward compat, just fix values)

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T4 for graph structure changes)
  - **Parallel Group**: Wave 2
  - **Blocks**: T13, T14
  - **Blocked By**: T4

  **References**:
  - `src/streaming_pipeline.py:243-284` — current metric computation
  - `src/streaming_pipeline.py:266-267` — threshold + anomalous_paths definition
  - `src/streaming_pipeline.py:269-276` — current detected_pairs extraction (only checks red_pairs)

  **Acceptance Criteria**:
  - [ ] FPR denominator = false_positives + true_negatives (pair-space)
  - [ ] Precision denominator = total anomalous pairs (pair-space)
  - [ ] Recall unchanged (already in pair-space)
  - [ ] No mixing of edge-space and pair-space counts

  **QA Scenarios**:
  ```
  Scenario: Metrics are in pair-space
    Tool: Bash
    Steps:
      1. Read streaming_pipeline.py lines ~270-290
      2. Verify no `anomalous_edge_count` variable
      3. Verify `anomalous_pairs` set is used for FPR and precision
      4. Verify `graph_edges` (pair set) is used as total universe
    Expected Result: All metric computations use pair-space consistently
    Evidence: .sisyphus/evidence/task-5-metrics-pair-space.txt
  ```

  **Commit**: YES
  - Message: `fix(metrics): compute FPR/precision/recall consistently in pair-space`
  - Files: `src/streaming_pipeline.py`

- [x] 6. Fix DAPT baselines — use continuous scores for roc_auc_score

  **What to do**:
  - `src/baselines/dapt_baselines.py:45-64` (`_evaluate`): Accept continuous scores instead of binary predictions
  - Change `_evaluate` signature to accept `y_scores: np.ndarray` (continuous) + `y_true: np.ndarray`
  - Compute binary predictions from scores using threshold
  - For OneClassSVM: use `model.decision_function(X_test)` — returns continuous anomaly scores (more negative = more anomalous)
  - For IsolationForest: use `model.score_samples(X_test)` — returns continuous anomaly scores (lower = more anomalous)
  - In `_evaluate`, compute AUC from continuous scores, compute F1/precision/recall from binary predictions (anomaly = score < threshold)
  - For OneClassSVM threshold: `0.0` (decision_function boundary)
  - For IsolationForest threshold: `0.0` (score_samples, or use `model.threshold_` if available, else `-0.5`)

  **Updated _evaluate**:
  ```python
  def _evaluate(y_true: np.ndarray, y_scores: np.ndarray, method_name: str, threshold: float = 0.0) -> dict:
      auc = roc_auc_score(y_true, y_scores)
      y_pred = (y_scores < threshold).astype(int)  # lower score = more anomalous
      f1 = f1_score(y_true, y_pred, zero_division=0)
      recall = recall_score(y_true, y_pred, zero_division=0)
      precision = precision_score(y_true, y_pred, zero_division=0)
      tn = np.sum((y_true == 0) & (y_pred == 0))
      fp = np.sum((y_true == 0) & (y_pred == 1))
      fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
      return {...}
  ```

  **Updated run_oneclass_svm**:
  ```python
  scores = model.decision_function(X_test)  # continuous, more negative = anomalous
  return _evaluate(y_test.values, scores, "oneclass_svm", threshold=0.0)
  ```

  **Updated run_isolation_forest**:
  ```python
  scores = model.score_samples(X_test)  # continuous, lower = anomalous
  return _evaluate(y_test.values, scores, "isolation_forest", threshold=-0.5)
  ```

  **Must NOT do**:
  - Do NOT modify `dapt_loader.py`
  - Do NOT change the return dict structure

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T1 — dapt_baselines.py may reference deleted modules)
  - **Parallel Group**: Wave 2
  - **Blocks**: T14
  - **Blocked By**: T1

  **References**:
  - `src/baselines/dapt_baselines.py:45-64` — current `_evaluate` with binary predictions
  - `src/baselines/dapt_baselines.py:67-84` — `run_oneclass_svm`
  - `src/baselines/dapt_baselines.py:87-107` — `run_isolation_forest`
  - sklearn docs: `OneClassSVM.decision_function()` returns (n_samples,) float array, positive = inlier
  - sklearn docs: `IsolationForest.score_samples()` returns (n_samples,) float array, higher = more normal

  **Acceptance Criteria**:
  - [ ] `roc_auc_score` receives continuous scores, not binary
  - [ ] `_evaluate` signature accepts continuous `y_scores` + `threshold`
  - [ ] OneClassSVM uses `decision_function()`
  - [ ] IsolationForest uses `score_samples()`
  - [ ] DAPT AUC is between 0.3 and 0.99 (not exactly 0.5)

  **QA Scenarios**:
  ```
  Scenario: DAPT AUC is non-degenerate
    Tool: Bash
    Steps:
      1. uv run python -c "
from src.baselines.dapt_baselines import run_dapt_baselines
results = run_dapt_baselines(data_dir='data/DAPT2020')
for r in results:
    print(f'{r[\"method_name\"]}: auc={r[\"auc\"]}, f1={r[\"f1\"]}')
    assert r['auc'] != 0.5 or r['f1'] > 0, f'Degenerate AUC for {r[\"method_name\"]}'
print('DAPT baselines OK')
"
    Expected Result: AUC values not exactly 0.5, F1 > 0
    Evidence: .sisyphus/evidence/task-6-dapt-auc.txt
  ```

  **Commit**: YES
  - Message: `fix(dapt): use continuous scores for roc_auc_score`
  - Files: `src/baselines/dapt_baselines.py`

- [x] 7. Fix edge rarity to use event count (weight) not pair_count

  **What to do**:
  - `src/features.py:85-117` (`extract_edge_features`): Edge rarity currently computes `1/pair_count` where `pair_count` is the number of igraph edges with same (src,dst). Since `StreamingGraphBuilder` deduplicates edges (one igraph edge per unique pair), `pair_count` is always 1, making edge_rarity always 1.0.
  - Fix: Use the `weight` attribute (event count from StreamingGraphBuilder) instead of pair_count:
    ```python
    for i in range(n):
        src_name = g.es[i].source_vertex["name"]
        dst_name = g.es[i].target_vertex["name"]
        weight = g.es[i].attributes().get("weight", 1)
        total_events = sum(g.es[j].attributes().get("weight", 1) for j in range(n) if g.es[j].source_vertex["name"] == src_name)
        edge_rarity[i] = 1.0 / weight  # rarer = fewer events on this edge
    ```
  - Actually simpler and more correct: edge_rarity should be `1/weight` since weight = event count. An edge with many events is "normal" (common), low weight = "rare" (suspicious).
  - Remove the pair_count computation entirely (it's now useless since pair_count==1 always)
  - Also fix `src_out_deg[i]` and `dst_in_deg[i]` to use precomputed arrays instead of per-edge property access (but this is T10 — keep separate. Just fix rarity here.)

  **Must NOT do**:
  - Do NOT change `extract_node_features` or `extract_graph_features`
  - Do NOT change the DataFrame output columns

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T4 — needs weight attribute from fixed _add_edge)
  - **Parallel Group**: Wave 2
  - **Blocks**: T9, T14
  - **Blocked By**: T4

  **References**:
  - `src/features.py:85-117` — current `extract_edge_features`
  - `src/streaming_pipeline.py:54-58` — `_add_edge` sets `weight` attribute (event count)

  **Acceptance Criteria**:
  - [ ] Edge rarity uses `weight` attribute (event count)
  - [ ] Edge rarity no longer always 1.0
  - [ ] `pair_count` dict removed

  **QA Scenarios**:
  ```
  Scenario: Edge rarity varies based on weight
    Tool: Bash
    Steps:
      1. uv run python -c "
import igraph as ig
g = ig.Graph(directed=True)
g.add_vertex('C1'); g.add_vertex('C2'); g.add_vertex('C3')
g.add_edge('C1','C2',weight=100,type='flow')
g.add_edge('C1','C3',weight=2,type='flow')
from src.features import extract_edge_features
ef = extract_edge_features(g)
rarity = ef['edge_rarity'].tolist()
assert rarity[0] == 1/100, f'Expected 0.01, got {rarity[0]}'
assert rarity[1] == 1/2, f'Expected 0.5, got {rarity[1]}'
assert rarity[0] != rarity[1], 'Rarity should differ'
print('Edge rarity varies correctly')
"
    Expected Result: edge_rarity[0]=0.01, edge_rarity[1]=0.5
    Evidence: .sisyphus/evidence/task-7-edge-rarity.txt
  ```

  **Commit**: YES
  - Message: `fix(features): edge rarity uses event count (weight) not pair_count`
  - Files: `src/features.py`

- [x] 8. Refactor scorer parallel path enum — no igraph pickling

  **What to do**:
  - Refactor `_enumerate_paths_for_nodes` to accept lightweight data structures instead of `ig.Graph`:
    - `adjacency: dict[int, list[tuple[int, int]]]` — maps src_node_idx → [(edge_id, dst_node_idx), ...]
    - `edge_scores_arr: np.ndarray` — already passed
    - `node_names: list[str]` — for path_nodes output
    - `max_hops: int` — already passed
  - Build adjacency dict + node_names from igraph once in `score_paths()` before dispatching to workers
  - This eliminates pickling the entire igraph object per worker (major memory/time savings)
  - `score_paths` becomes:
    ```python
    def score_paths(g, edge_scores, max_hops=4, top_k=50):
        total_nodes = g.vcount()
        n_workers = min(os.cpu_count() or 1, 6)
        edge_scores_arr = edge_scores.values

        # Build lightweight adjacency (only top-10 scored edges per node)
        node_names = [g.vs[i]["name"] for i in range(total_nodes)]
        adjacency: dict[int, list[tuple[int, int]]] = {}
        for src in range(total_nodes):
            out_eids = g.incident(src, mode="out")
            if out_eids:
                scored = sorted(out_eids, key=lambda eid: edge_scores_arr[eid], reverse=True)[:10]
                adjacency[src] = [(eid, g.es[eid].target) for eid in scored]

        # Build target lookup for edge → dst node
        edge_targets = np.array([g.es[i].target for i in range(g.ecount())])

        if n_workers <= 1 or total_nodes < n_workers * 10:
            all_paths = _enumerate_paths_for_nodes(adjacency, edge_scores_arr, node_names, edge_targets, list(range(total_nodes)), max_hops)
        else:
            # ... same chunking logic, but pass lightweight data
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                futures = [
                    pool.submit(_enumerate_paths_for_nodes, adjacency, edge_scores_arr, node_names, edge_targets, chunk, max_hops)
                    for chunk in node_chunks
                ]
            ...
    ```
  - `_enumerate_paths_for_nodes` signature becomes:
    ```python
    def _enumerate_paths_for_nodes(
        adjacency: dict[int, list[tuple[int, int]]],
        edge_scores_arr: np.ndarray,
        node_names: list[str],
        edge_targets: np.ndarray,
        node_indices: list[int],
        max_hops: int,
    ) -> list[dict]:
    ```
  - Inside, replace `g.incident()` with `adjacency.get(node, [])`, `g.es[eid].target` with `edge_targets[eid]`, `g.vs[idx]["name"]` with `node_names[idx]`

  **Must NOT do**:
  - Do NOT change the path scoring formula
  - Do NOT change top_k or max_hops defaults
  - Do NOT remove ProcessPoolExecutor (keep parallel path)

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T4 for graph structure)
  - **Parallel Group**: Wave 3
  - **Blocks**: T14
  - **Blocked By**: T4

  **References**:
  - `src/scorer.py:21-82` — current `_enumerate_paths_for_nodes` using igraph
  - `src/scorer.py:177-231` — current `score_paths` with ProcessPoolExecutor
  - igraph API: `g.incident(v, mode="out")` → list of edge IDs
  - igraph API: `g.es[eid].target` → destination vertex index
  - igraph API: `g.vs[idx]["name"]` → vertex name attribute

  **Acceptance Criteria**:
  - [ ] `_enumerate_paths_for_nodes` does NOT take `ig.Graph` parameter
  - [ ] No igraph object is pickled/sent to worker processes
  - [ ] `score_paths` still uses ProcessPoolExecutor for parallel path
  - [ ] Path output format identical (same dict keys)

  **QA Scenarios**:
  ```
  Scenario: Path enumeration works with lightweight data
    Tool: Bash
    Steps:
      1. uv run python -c "
import igraph as ig
import numpy as np
g = ig.Graph(directed=True)
for i in range(20):
    g.add_vertex(f'C{i}')
for i in range(19):
    g.add_edge(i, i+1, weight=1, type='flow')
g.add_edge(0, 19, weight=1, type='flow')
from src.scorer import score_paths
scores = np.random.rand(g.ecount())
import pandas as pd
edge_scores = pd.Series(scores, index=pd.Index(range(g.ecount()), name='edge_index'))
paths = score_paths(g, edge_scores, max_hops=3, top_k=10)
assert len(paths) > 0, 'No paths found'
assert 'path_score' in paths.columns
assert 'path_nodes' in paths.columns
assert all(isinstance(n, str) for n in paths['path_nodes'].iloc[0]), 'path_nodes should be list of strings'
print(f'Found {len(paths)} paths, top score={paths[\"path_score\"].iloc[0]:.4f}')
print('Path enumeration OK')
"
    Expected Result: Paths found, path_nodes are strings, scores > 0
    Evidence: .sisyphus/evidence/task-8-parallel-paths.txt
  ```

  **Commit**: YES
  - Message: `perf(scorer): refactor parallel path enum to avoid igraph pickling`
  - Files: `src/scorer.py`

- [x] 9. Merge auth_failure + port_diversity into single pass

  **What to do**:
  - `src/scorer.py:85-134`: `_compute_auth_failure_rate` and `_compute_port_diversity` both iterate all edges separately (each O(n) with separate loops). Merge into a single function `_compute_edge_source_stats(g)` that does one pass over all edges.
  - New function:
    ```python
    def _compute_edge_source_stats(g: ig.Graph) -> tuple[list[float], list[float]]:
        """Single-pass computation of auth_failure_rate and port_diversity per edge."""
        n = g.ecount()

        # Collect per-source stats
        src_auth_failures: dict[int, int] = {}
        src_auth_total: dict[int, int] = {}
        src_ports: dict[int, set[str]] = {}
        src_flow_total: dict[int, int] = {}

        for i in range(n):
            attrs = g.es[i].attributes()
            src = g.es[i].source
            edge_type = attrs.get("type", "")

            if edge_type == "auth":
                src_auth_total[src] = src_auth_total.get(src, 0) + 1
                if attrs.get("success") != "1":
                    src_auth_failures[src] = src_auth_failures.get(src, 0) + 1
            elif edge_type == "flow":
                src_flow_total[src] = src_flow_total.get(src, 0) + 1
                port = str(attrs.get("dst_port", ""))
                if src not in src_ports:
                    src_ports[src] = set()
                src_ports[src].add(port)

        # Compute per-source rates
        src_failure_rate = {src: src_auth_failures.get(src, 0) / total for src, total in src_auth_total.items()}
        src_diversity = {src: len(src_ports[src]) / total for src, total in src_flow_total.items() if total > 0}

        # Map to per-edge arrays
        auth_fail = [src_failure_rate.get(g.es[i].source, 0.0) for i in range(n)]
        port_div = [src_diversity.get(g.es[i].source, 0.0) for i in range(n)]

        return auth_fail, port_div
    ```
  - Update `score_edges` to call `_compute_edge_source_stats` once instead of two separate calls

  **Must NOT do**:
  - Do NOT change the scoring formula
  - Do NOT change the output format of `score_edges`

  **Recommended Agent Profile**:
  - **Category**: `unspecified-high`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO (depends on T7 for rarity fix context)
  - **Parallel Group**: Wave 3
  - **Blocks**: T14
  - **Blocked By**: T7

  **References**:
  - `src/scorer.py:85-108` — `_compute_auth_failure_rate` (current)
  - `src/scorer.py:111-134` — `_compute_port_diversity` (current)
  - `src/scorer.py:146-174` — `score_edges` calls both separately

  **Acceptance Criteria**:
  - [ ] Single function `_compute_edge_source_stats` replaces two separate functions
  - [ ] `score_edges` calls it once
  - [ ] Old `_compute_auth_failure_rate` and `_compute_port_diversity` removed
  - [ ] Edge scores produce same relative ordering

  **QA Scenarios**:
  ```
  Scenario: Single-pass produces same results
    Tool: Bash
    Steps:
      1. uv run python -c "
import igraph as ig, numpy as np, pandas as pd
g = ig.Graph(directed=True)
g.add_vertex('C1'); g.add_vertex('C2'); g.add_vertex('C3')
g.add_edge(0, 1, type='auth', success='1', weight=5)
g.add_edge(0, 2, type='auth', success='0', weight=3)
g.add_edge(1, 2, type='flow', dst_port='80', weight=10)
from src.scorer import score_edges
ef = pd.DataFrame({'edge_rarity': [0.2, 0.33, 0.1], 'src_out_degree': [2,2,1], 'dst_in_degree': [1,2,2]})
scores = score_edges(g, ef)
assert len(scores) == 3
assert all(0 <= s <= 1 for s in scores)
print(f'Scores: {scores.tolist()}')
print('Single-pass scoring OK')
"
    Expected Result: 3 scores, all in [0,1]
    Evidence: .sisyphus/evidence/task-9-single-pass.txt
  ```

  **Commit**: YES
  - Message: `perf(scorer): merge auth_failure + port_diversity into single pass`
  - Files: `src/scorer.py`

- [x] 10. Precompute degree arrays in features.py

  **What to do**:
  - `src/features.py:100-106`: Currently calls `g.es[i].source_vertex.outdegree()` and `g.es[i].target_vertex.indegree()` per edge — this is a property lookup via igraph's attribute system on every iteration.
  - Precompute `indegree()` and `outdegree()` arrays once, then look up by vertex index:
    ```python
    out_deg_arr = g.outdegree()
    in_deg_arr = g.indegree()
    source_indices = [g.es[i].source for i in range(n)]
    target_indices = [g.es[i].target for i in range(n)]
    src_out_deg = [out_deg_arr[src_idx] for src_idx in source_indices]
    dst_in_deg = [in_deg_arr[tgt_idx] for tgt_idx in target_indices]
    ```
  - Also precompute `source_indices` and `target_indices` since they're used in T9's `_compute_edge_source_stats` too

  **Must NOT do**:
  - Do NOT change the output DataFrame columns
  - Do NOT change `extract_node_features` or `extract_graph_features`

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T8, T9, T11)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/features.py:100-106` — current per-edge property access

  **Acceptance Criteria**:
  - [ ] No `source_vertex.outdegree()` or `target_vertex.indegree()` calls in loop
  - [ ] `outdegree()` and `indegree()` called once, indexed by precomputed arrays
  - [ ] Output DataFrame identical

  **QA Scenarios**:
  ```
  Scenario: Precomputed degrees match property access
    Tool: Bash
    Steps:
      1. uv run python -c "
import igraph as ig
g = ig.Graph(directed=True)
for i in range(10): g.add_vertex(f'C{i}')
import random
random.seed(42)
for _ in range(20):
    s,t = random.randint(0,9), random.randint(0,9)
    if s != t: g.add_edge(s, t, weight=1, type='flow')
from src.features import extract_edge_features
ef = extract_edge_features(g)
assert 'src_out_degree' in ef.columns
assert 'dst_in_degree' in ef.columns
assert all(ef['src_out_degree'] >= 0)
assert all(ef['dst_in_degree'] >= 0)
print(f'Edge features: {len(ef)} rows')
print('Precomputed degrees OK')
"
    Expected Result: Edge features with valid degree columns
    Evidence: .sisyphus/evidence/task-10-precomputed-degrees.txt
  ```

  **Commit**: YES
  - Message: `perf(features): precompute degree arrays for edge features`
  - Files: `src/features.py`

- [x] 11. Fix clustering coefficient on directed graph

  **What to do**:
  - `src/features.py:124`: `g.transitivity_local_undirected(mode="zero")` is called on a directed graph. igraph silently computes undirected clustering, but this is semantically misleading.
  - Fix: Convert to undirected copy first, then compute clustering:
    ```python
    "avg_clustering": float(np.mean(g.to_undirected().transitivity_local_undirected(mode="zero"))),
    ```
  - Or add a comment explaining the intentional conversion. Either way, the intent should be clear.

  **Must NOT do**:
  - Do NOT use directed clustering (igraph doesn't have a native one, and standard practice for threat graphs is undirected)
  - Do NOT change other feature computations

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 3 (with T8, T9, T10)
  - **Blocks**: None
  - **Blocked By**: None

  **References**:
  - `src/features.py:120-128` — `extract_graph_features`
  - igraph docs: `transitivity_local_undirected` computes on undirected version of the graph internally

  **Acceptance Criteria**:
  - [ ] Code explicitly uses `g.to_undirected()` before clustering OR has clear comment
  - [ ] Feature values unchanged (same computation, just explicit)

  **QA Scenarios**:
  ```
  Scenario: Clustering uses undirected graph explicitly
    Tool: Bash
    Steps:
      1. grep -n "transitivity_local_undirected\|to_undirected" src/features.py
    Expected Result: Both `to_undirected()` and `transitivity_local_undirected` appear in extract_graph_features
    Evidence: .sisyphus/evidence/task-11-clustering.txt
  ```

  **Commit**: YES
  - Message: `fix(features): use undirected copy for clustering coefficient`
  - Files: `src/features.py`

- [x] 12. Fix double red-team load in run_experiment.py

  **What to do**:
  - `run_experiment.py:142-144`: Loads redteam data AGAIN (via `load_redteam()`) even though it was already loaded inside `run_streaming_experiment()`. Redundant I/O.
  - Fix: Pass red team data from `run_streaming_experiment` via `viz_data`. Add `viz_data["red_pairs"]` to the viz_data dict in streaming_pipeline.py (after line 188).
  - In `run_experiment.py`, replace lines 141-144 with `red_pairs = viz_data.get("red_pairs", set())`.
  - Remove the `from src.data_loader import load_redteam` import in run_experiment.py if no longer needed.

  **Must NOT do**:
  - Do NOT change visualization output
  - Do NOT change redteam loading in data_loader.py

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T13)
  - **Blocks**: T14
  - **Blocked By**: None

  **References**:
  - `run_experiment.py:139-144` — duplicate redteam load
  - `src/streaming_pipeline.py:187-188` — redteam already loaded here

  **Acceptance Criteria**:
  - [ ] `load_redteam` not called in run_experiment.py
  - [ ] `red_pairs` read from `viz_data`

  **QA Scenarios**:
  ```
  Scenario: No duplicate redteam load
    Tool: Bash
    Steps:
      1. grep -c "load_redteam" run_experiment.py
    Expected Result: 0
    Evidence: .sisyphus/evidence/task-12-no-dup-load.txt
  ```

  **Commit**: YES
  - Message: `fix(experiment): remove duplicate red-team load`
  - Files: `run_experiment.py, src/streaming_pipeline.py`

- [x] 13. Handle degenerate threshold case

  **What to do**:
  - `streaming_pipeline.py:266`: `np.percentile(edge_scores.values, 95)` — if all edge scores identical, threshold equals score, flags everything.
  - Fix: After computing threshold, check if std is near-zero:
    ```python
    threshold = float(np.percentile(edge_scores.values, 95)) if len(edge_scores) > 0 else 0.5
    if len(edge_scores) > 0 and edge_scores.std() < 1e-10:
        logger.warning("  All edge scores identical — no anomalies detectable")
        threshold = float(edge_scores.max()) + 0.01
    ```

  **Must NOT do**:
  - Do NOT change percentile (95th) default
  - Do NOT change detection logic beyond threshold guard

  **Recommended Agent Profile**:
  - **Category**: `quick`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: YES
  - **Parallel Group**: Wave 4 (with T12)
  - **Blocks**: T14
  - **Blocked By**: T5

  **References**:
  - `src/streaming_pipeline.py:266`

  **Acceptance Criteria**:
  - [ ] Degenerate case handled (no flag-all)
  - [ ] Warning logged
  - [ ] Normal case unchanged

  **QA Scenarios**:
  ```
  Scenario: Uniform scores don't flag everything
    Tool: Bash
    Steps:
      1. uv run python -c "
import numpy as np, pandas as pd
scores = pd.Series([0.5]*100)
threshold = float(np.percentile(scores.values, 95))
if scores.std() < 1e-10:
    threshold = float('inf')
assert threshold > scores.max(), 'Should not flag all'
print('Degenerate threshold handled')
"
    Expected Result: threshold > max score
    Evidence: .sisyphus/evidence/task-13-degenerate-threshold.txt
  ```

  **Commit**: YES
  - Message: `fix(pipeline): handle degenerate threshold case`
  - Files: `src/streaming_pipeline.py`

- [ ] 14. Full pipeline smoke test

  **What to do**:
  - Run: `uv run python run_experiment.py --data-dir data/LANL-Dataset-2015 --dapt-dir data/DAPT2020`
  - Verify exit code 0
  - Read `metrics.csv` from latest results dir
  - Assert: 5+ rows, no NaN/inf, DAPT AUC != 0.5, all metrics in [0,1]
  - Check figures/ directory has PNG files

  **Must NOT do**:
  - Do NOT modify any source code

  **Recommended Agent Profile**:
  - **Category**: `deep`
  - **Skills**: []

  **Parallelization**:
  - **Can Run In Parallel**: NO
  - **Parallel Group**: Wave 4 (after T12, T13)
  - **Blocks**: F1-F4
  - **Blocked By**: T5, T6, T7, T8, T9, T12, T13

  **References**:
  - `run_experiment.py` — orchestrator
  - Output: `results/<timestamp>/metrics.csv`

  **Acceptance Criteria**:
  - [ ] Exit code 0
  - [ ] 5+ rows in metrics.csv
  - [ ] No NaN/inf
  - [ ] DAPT AUC between 0.3 and 0.99
  - [ ] Figures generated

  **QA Scenarios**:
  ```
  Scenario: Full pipeline run succeeds
    Tool: Bash
    Steps:
      1. uv run python run_experiment.py --data-dir data/LANL-Dataset-2015 --dapt-dir data/DAPT2020
      2. Find latest results dir
      3. Validate metrics.csv
      4. Check figures exist
    Expected Result: Exit code 0, valid metrics, figures present
    Evidence: .sisyphus/evidence/task-14-full-pipeline.txt
  ```

  **Commit**: YES
  - Message: `test: full pipeline smoke test`
  - Files: (no code changes)

---

## Final Verification Wave (MANDATORY)

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read plan end-to-end. For each "Must Have": verify implementation exists (read file, run command). For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist. Compare deliverables against plan.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT: APPROVE/REJECT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run `uv run python -c "import src.streaming_pipeline; import src.scorer; import src.features; import src.data_loader; import src.baselines.dapt_baselines"` to verify imports. Check for: `as any`, `@ts-ignore` equivalents, empty catches, console.log equivalents, unused imports. Check AI slop patterns.
  Output: `Imports [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real Manual QA** — `unspecified-high`
  Run `uv run python run_experiment.py --data-dir data/LANL-Dataset-2015 --dapt-dir data/DAPT2020`. Verify exit code 0. Read output metrics.csv. Verify all metrics non-zero, DAPT AUC not exactly 0.5.
  Output: `Pipeline [PASS/FAIL] | Metrics [N/N valid] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  For each task: read "What to do", read actual diff. Verify 1:1. Check "Must NOT do" compliance. Detect cross-task contamination.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N issues] | VERDICT`

---

## Commit Strategy

- **T1**: `cleanup: remove dead code (evaluate.py, graph_builder.py, single_source.py, main.py)`
- **T2**: `fix(pipeline): correct return type annotation + remove dead vars`
- **T3**: `perf(loader): use bisect for O(log n) window membership`
- **T4**: `fix(pipeline): preserve first_time on duplicate edges + add user-user auth edges`
- **T5**: `fix(metrics): compute FPR/precision/recall consistently in pair-space`
- **T6**: `fix(dapt): use continuous scores for roc_auc_score`
- **T7**: `fix(features): edge rarity uses event count (weight) not pair_count`
- **T8**: `perf(scorer): refactor parallel path enum to avoid igraph pickling`
- **T9**: `perf(scorer): merge auth_failure + port_diversity into single pass`
- **T10**: `perf(features): precompute degree arrays for edge features`
- **T11**: `fix(features): use undirected copy for clustering coefficient`
- **T12**: `fix(experiment): remove duplicate red-team load`
- **T13**: `fix(pipeline): handle degenerate threshold case`
- **T14**: `test: full pipeline smoke test`

---

## Success Criteria

### Verification Commands
```bash
# No import errors
uv run python -c "from src.streaming_pipeline import run_streaming_experiment; from src.scorer import score_edges, score_paths, score_graph; from src.features import extract_all_features; from src.data_loader import _time_in_any_window; from src.baselines.dapt_baselines import run_dapt_baselines"

# Full pipeline run
uv run python run_experiment.py --data-dir data/LANL-Dataset-2015 --dapt-dir data/DAPT2020

# Dead files gone
test ! -f src/evaluate.py && test ! -f src/graph_builder.py && test ! -f src/baselines/single_source.py && test ! -f main.py

# Metrics non-degenerate
uv run python -c "
import pandas as pd, json, glob
dirs = sorted(glob.glob('results/2*'))
latest = dirs[-1]
df = pd.read_csv(f'{latest}/metrics.csv')
print(df[['method','recall','fpr','f1','auc']].to_string())
assert all(df['recall'] >= 0), 'recall negative'
assert all(df['fpr'] >= 0), 'fpr negative'
assert all(df['f1'] >= 0), 'f1 negative'
print('All metrics non-negative')
"
```

### Final Checklist
- [ ] All "Must Have" present
- [ ] All "Must NOT Have" absent
- [ ] Pipeline completes with exit code 0
- [ ] DAPT AUC not exactly 0.5
- [ ] No import errors
- [ ] Dead files deleted
