# Feature Audit After the Duplicate-Feature Bug Fix

## Why this report exists

The feature audit currently published in `report/Feature_Audit_Results.md` was generated on `2026-05-12` against `results/20260504_183345/combined/edge_features.csv` — a cached pipeline output produced **before** the duplicate-feature bug fix (commit `4531234`) was merged into `main`. That audit therefore reflects buggy values for two specific feature columns in the input data: `weight_norm` was a literal copy of `edge_rarity`, and `source_fan_out` was a literal copy of `src_out_degree`. The audit module itself is correct; only its input was stale.

The natural way to refresh the audit is to re-run the pipeline against the LANL-2015 dataset on the corrected `main`. That requires the raw dataset on the executing machine, which is not present here. As a substitute, this report uses a shorter path: rebuild the `igraph.Graph` object from the cached `graph_edges.csv` (which is unaffected by the bug, since the graph builder runs before `extract_edge_features`), then run the actual fixed `extract_edge_features` from `src/features/edge.py` on it. This bypasses the multi-hour graph-construction step and produces a refreshed `edge_features.csv` using the same production code paths the pipeline would use, just without needing the raw dataset.

The refreshed feature matrix was written to `results/20260512_post_fix/combined/edge_features.csv`. A new audit was run on this directory with the same configuration as the published audit (`holdout_frac=0.5`, `min_auc=0.6`, log1p transformations applied to the same six degree features, seed `42`). The results are stored at `feature_results/20260513_012847/`.

## What changed

The before-and-after comparison is dominated by one substantive change and several smaller artifacts.

### `source_fan_out` recovers the signal the bug was hiding

Before the fix, `source_fan_out` in `edge_features.csv` was computed as `out_deg[sources]` — the raw out-degree of the source node, which is also stored in `src_out_degree`. After feature standardization and StandardScaler, those two columns produced identical values; the audit correctly flagged them as duplicates, and `source_fan_out` ended up with single-feature AUC 0.217 (essentially the sign-flipped reading of `src_out_degree`). With the fix, `source_fan_out` is now computed as `out_deg / (out_deg + in_deg)` — the fan-out ratio the methodology section has always described. The single-feature AUC on the calibration half jumps to **0.906**, second-strongest behind only `is_ntlm` (AUC 0.933). Red-team source nodes have a mean fan-out ratio of 0.974; benign source nodes have a mean of 0.696. The structural asymmetry that the methodology section predicted — attackers behaving like near-pure source nodes — is finally being captured at the edge level.

### `src_fan_out_ratio` drops out of the feature pool

The audit module joins per-source and per-destination node features onto every edge via `src/feature_audit/joiner.py`, with a deduplication step that removes joined columns identical to existing edge-level columns. Before the fix, the joined `src_fan_out_ratio` (computed correctly from `node_features.csv`) was distinct from the buggy edge-level `source_fan_out`, so both appeared in the feature pool. After the fix, the corrected edge-level `source_fan_out` is mathematically identical to `src_fan_out_ratio`, so the join deduplication removes the latter. The audit's #2 feature is the same signal as before; only the column it sits under has changed names.

### `weight_norm` is now selected, with a caveat

Before the fix, `weight_norm = edge_rarity.copy()` produced byte-identical columns, the duplicate detector flagged them at correlation 1.0, and `weight_norm` was excluded from selection. After the fix, `weight_norm = weight / max(weight)` is monotonically anti-correlated with `edge_rarity = 1 / weight`. Their ranks are perfectly inverted but their raw-value correlation is roughly $-0.85$ — well below the duplicate-detection threshold of $|r| > 0.999$. The audit therefore selects both features. This is technically a redundancy: any rank-based detector (Isolation Forest, AUC scoring) extracts identical information from either of them. The duplicate detector's correlation threshold is too strict to catch rank-equivalence-via-monotonic-transform; a Spearman correlation or a small rank-equivalence test would catch this. For now, the audit selects both, and downstream rank-based detectors will not be harmed; distance-based detectors (LOF, OCSVM with RBF) will see modest over-weighting along the weight axis.

### Selection cardinality moves from 20 to 21

The published audit selected 20 features at `min_auc=0.6`. The refreshed audit selects 21. The net change is: `src_fan_out_ratio` drops out (de-duplicated against the corrected `source_fan_out`), `source_fan_out` enters (was excluded as a buggy duplicate, now is the strong feature), and `weight_norm` enters as an effective duplicate of `edge_rarity` (the +1 to cardinality). The set of *distinct* informational signals captured by the selection is unchanged from the published audit; only the labeling of features has shifted.

## A side-effect of the rebuild-from-CSV shortcut

The rebuild path used here loses one signal that the pipeline normally captures. The cached `graph_edges.csv` stores `dst_port` as a string column with mixed types ("445.0", "N10", `NaN`), because pandas writes the column as `object` when some rows are non-numeric. The `extract_edge_features` function reads `dst_port` from the graph object and attempts `int(dp)` to compare against the lateral-movement port set. On a string value like `"445.0"`, `int(...)` raises `ValueError` and the corresponding `is_unusual_dst_port` entry stays at zero. The rebuilt feature matrix therefore has `is_unusual_dst_port == 0` for every edge. In the published audit (operating on the original `edge_features.csv` produced directly by the pipeline, not from a CSV round-trip), `is_unusual_dst_port` had a small number of nonzero entries (benign mean 0.018, red-team mean 0.013).

This artifact is immaterial to the substantive findings: `is_unusual_dst_port` had calibration-half AUC 0.503 in the published audit — essentially random — and is not selected in either audit. But it underscores that the rebuild-from-CSV shortcut is a stand-in for the full pipeline re-run rather than a replacement for it. A genuine refresh requires the team to re-run `main.py` on a machine that has the LANL-2015 dataset, with the bug fix in `main`, and then re-run `feature.py` against that fresh output. The numbers reported here will agree with that future fresh-run audit for every feature except `is_unusual_dst_port`.

## Headline before/after table

The comparison below uses the published audit at `report/Feature_Audit_Results.md` (pre-fix) as the baseline and the refreshed audit at `feature_results/20260513_012847/` (post-fix) as the comparator. AUC is the single-feature AUC on the calibration half, with sign-flipping applied for reverse-correlated features.

| Feature | Pre-fix AUC | Post-fix AUC | Pre-fix selected | Post-fix selected | Note |
|---|---|---|---|---|---|
| `is_ntlm` | 0.9328 | 0.9328 | yes | yes | unchanged |
| `source_fan_out` | 0.2172 | **0.9060** | no | yes | **bug fix: was buggy duplicate of `src_out_degree`; now correct ratio** |
| `src_fan_out_ratio` | 0.9060 | — | yes | — | dropped from pool (now identical to corrected `source_fan_out`) |
| `weight_norm` | 0.8085 | 0.8085 | no (flagged as duplicate) | yes | rank-equivalent to `edge_rarity`; corrcoef-based dedup no longer flags |
| `edge_rarity` | 0.8085 | 0.8085 | yes | yes | unchanged |
| `is_unusual_dst_port` | 0.5025 | 0.5000 | no | no | artifact of CSV-rebuild shortcut (lost a small amount of signal) |
| all other features | unchanged | unchanged | matching | matching | the bug only affected the two columns above |
| selected count | 20 | 21 | | | net +1 from `weight_norm` entering as an undetected rank-duplicate of `edge_rarity` |

## What downstream consumers should do

The published audit reflects a state of the world that no longer exists in `main`. Two practical follow-ups are appropriate.

First, re-run the pipeline against the LANL-2015 dataset on a machine that has the data, with the current `main` (which includes commit `4531234`), and then re-run `feature.py` against that fresh output. The resulting audit should agree with this report on every feature except possibly `is_unusual_dst_port`, where this report carries a small downward bias. The `report/Feature_Audit_Results.md` file should be replaced with the fresh-run output once available.

Second, consider tightening the duplicate-detection logic in `src/feature_audit/loader.py` to catch rank-equivalent features in addition to value-correlation duplicates. The current `np.corrcoef`-based check at threshold 0.999 misses the `weight_norm` / `edge_rarity` pair after the fix because their Pearson correlation is roughly $-0.85$ (monotonic but not linear). A Spearman rank correlation check, or a more direct rank-equivalence test, would catch this case. This is a refinement to the audit, not a blocker for using the current output.

## Status

This refresh closes the loop on the duplicate-feature bug discovered while preparing `report/Feature_Selection_Analysis.md`. The bug is fixed in `main`, the audit's interpretation has been recomputed under the fix, and the substantive finding — that the corrected `source_fan_out` is the second-strongest single feature, validating the structural asymmetry the methodology section predicted — is now reflected in a refreshed audit. The path forward for the paper is to use the post-fix audit as the canonical input to the held-out baseline-comparison work that remains pending in `Feature_Selection_Analysis.md`.
