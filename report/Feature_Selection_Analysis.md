# Feature Selection for the Tabular Baselines: PCA, Per-Feature Diagnostics, and Why We Should Avoid Information Leakage

## Motivation

Our paper compares the graph-based scoring method against unsupervised tabular detectors (Isolation Forest, One-Class SVM, and extensions). A natural question that arises in this comparison is which features the baselines should see. Three options have been on the table: (a) use all twelve edge features computed in `src/features/edge.py`, (b) restrict to the five features that also appear in the heuristic scoring formula (the convention adopted on `main` via `SCORING_FEATURE_COLUMNS` in `shared_baselines.py`), or (c) apply a principal-component projection and pass the leading components to the detectors. This document examines why option (c) is a poor fit for this problem, presents a per-feature discriminative diagnostic for the twelve raw features, and discusses the information-leakage hazard that arises when the same labels are used both to select features and to evaluate the resulting detector.

## Why PCA Is Not the Right Tool Here

Principal Component Analysis finds linear combinations of features that maximize variance. The implicit assumption is that high-variance directions are also high-relevance directions, but this assumption is exactly backwards for anomaly detection. The most discriminative features in our feature space are binary indicators such as `is_ntlm` and `is_network_logon`, whose variance is bounded by $p(1-p) \leq 0.25$ regardless of how strongly they separate red-team from benign edges. A continuous feature like `dst_in_degree` has a variance roughly $10^8$ times larger, simply because it is unbounded. PCA's first component would be dominated by `dst_in_degree` and the other unbounded features, and the binary indicators that actually carry the signal would land in the trailing components and be discarded under any reasonable dimensionality reduction.

PCA is also an unsupervised transformation. It has no access to the red-team labels and therefore no way to know which directions in feature space are discriminative for our specific task. For decision-tree-based detectors such as Isolation Forest, PCA preprocessing is additionally counterproductive because trees split on individual features and lose interpretability when those features are linear combinations of the originals. Empirically, the PCA-reconstruction baseline already in our comparison reaches only AUC 0.667 — the lowest of the five detectors — confirming on our data what the theory predicts.

The conclusion is that PCA is appropriate for visualization, decorrelation prior to a linear model, or compression when storage is constrained, but not for selecting features for an anomaly-detection comparison on a feature space dominated by binary and bounded-range indicators.

## Per-Feature Discriminative Diagnostic

To characterize which of the twelve edge features actually carry signal, we computed the single-feature AUC against the red-team labels for the full 364,802-edge LANL-2015 combined-graph feature matrix. For each feature we report the absolute AUC (with the sign flipped where the feature is reverse-correlated with the red-team label), the number of unique values, the variance, and the mean values restricted to red-team and benign edges. The results, sorted by AUC descending:

| Feature | AUC | Sign | Unique values | Mean (red-team) | Mean (benign) | In team's 5 |
|---|---|---|---|---|---|---|
| `is_ntlm` | 0.9327 | + | 2 | 0.967 | 0.102 | yes |
| `edge_rarity` | 0.8210 | + | 4,762 | 0.545 | 0.123 | yes |
| `weight_norm` | 0.8210 | + | 4,762 | 0.545 | 0.123 | no |
| `dst_in_degree` | 0.8185 | − | 195 | 724.9 | 6,196.7 | no |
| `is_network_logon` | 0.8170 | + | 2 | 0.974 | 0.340 | yes |
| `src_out_degree` | 0.7819 | + | 166 | 899.2 | 916.5 | no |
| `source_fan_out` | 0.7819 | + | 166 | 899.2 | 916.5 | no |
| `protocol_rarity` | 0.6369 | − | 5 | 0.005 | 0.142 | yes |
| `byte_per_packet` | 0.6369 | − | 21,428 | 0.001 | 0.029 | no |
| `is_success_auth` | 0.5922 | + | 2 | 0.875 | 0.691 | no |
| `duration_zscore` | 0.5621 | + | 75 | −0.004 | 0.000 | no |
| `is_unusual_dst_port` | 0.5059 | − | 2 | 0.007 | 0.018 | yes |

Three findings from this diagnostic are worth emphasizing.

First, the strongest single-feature discriminator by a wide margin is `is_ntlm`, with AUC 0.93. Among red-team edges, 96.7% use NTLM authentication; among benign edges, only 10.2% do. This is consistent with the domain knowledge that drove the original scoring formula: pass-the-hash and similar lateral-movement techniques rely heavily on NTLM. The empirical AUC validates the domain-knowledge weight assignment in `s_auth`.

Second, two pairs of features are mathematically redundant on this data. `edge_rarity` and `weight_norm` produce identical AUC (0.8210), identical means, and identical variances. The same holds for `src_out_degree` and `source_fan_out`. The diagnostic flagged this as a data observation, and tracing the cause turned out to identify a code bug rather than a coincidental statistical property — see the next section.

Third, and most consequential for our paper, `is_unusual_dst_port` — one of the five features in the team's `SCORING_FEATURE_COLUMNS` — has AUC 0.51, essentially indistinguishable from random. The feature flags destination ports associated with known lateral-movement services (22, 23, 445, 3389, 5985, 5986) and ephemeral ports above 49,152. The flag carries no discriminative signal on LANL-2015 red-team activity, because the red-team traffic in this dataset uses standard authentication ports rather than the flagged service ports. The feature was selected on the basis of prior-literature domain knowledge, not on observed discrimination, and the observed AUC indicates that this particular bit of prior knowledge does not transfer to this dataset. This is a defensible finding to report: domain heuristics that work on one network do not automatically work on another.

## Code Bug: Two Features Were Literal Copies of Other Features

Tracing the source of the perfect-duplicate finding above led to `src/features/edge.py`. The pipeline was computing two features as exact copies of two other features, contrary to what the methodology section of the paper describes those features as meaning. Specifically, the relevant lines on `main` at the time of this analysis were:

```python
edge_rarity = np.where(weights > 0, 1.0 / weights, 0.0)
weight_norm = edge_rarity.copy()   # bug: identical to edge_rarity

src_out_deg = out_deg[sources]
source_fan_out = out_deg[sources]  # bug: identical to src_out_degree
```

The intended definitions, per the methodology section, are: `weight_norm` should be a normalization of the edge weight (e.g., `weight / max(weight)`) producing values in $[0, 1]$, and `source_fan_out` should be a fan-out *ratio*, defined as `out_degree / (out_degree + in_degree)`, capturing how heavily a node's connectivity skews toward outgoing edges. Neither was being computed; the variable names referred to other features in the same assignment block.

The fix replaces these two lines with the intended formulas:

```python
max_weight = weights.max() if weights.size > 0 and weights.max() > 0 else 1.0
weight_norm = weights / max_weight

total_deg = out_deg + in_deg
source_fan_out = np.where(
    total_deg[sources] > 0, out_deg[sources] / total_deg[sources], 0.0
)
```

This change is isolated to seven lines of `src/features/edge.py` and does not affect column names, downstream consumers, or any test in the repository. The corrected pipeline output still produces the same set of fifteen edge-feature columns; only the values of the two corrected columns change.

The fix is committed on the branch `ip/fix-feature-duplicates` (commit `1e55dab`) as a separate, focused change so that the larger feature-selection analysis (this report) and the bug fix can be reviewed independently.

## Empirical Impact of the Fix

The fix is small in code but uneven in effect. One of the two features is corrected without recovering new signal; the other turns out to be one of the strongest discriminators in the entire feature set, previously hidden behind the duplicate. Re-computing per-feature AUC on the same 364,802-edge masked matrix using the corrected formulas yields the following:

| Feature | Old AUC (buggy duplicate) | New AUC (fixed) | Change |
|---|---|---|---|
| `weight_norm` | 0.821 | 0.821 | unchanged |
| `source_fan_out` | 0.782 | **0.905** | **+0.123** |

The `weight_norm` result deserves a brief explanation. The corrected `weight_norm = weight / max(weight)` is the *reciprocal-of-reciprocal* of `edge_rarity = 1 / weight`, so the two features rank the same edges in opposite directions. The signed AUC on the raw scores flips sign — the diagnostic AUC reported above is the absolute value after the standard sign-correction. Discriminative power is unchanged: any detector that uses one of these features gains nothing from also seeing the other. So the corrected `weight_norm` is no longer a literal copy of `edge_rarity` but encodes the same underlying signal in inverse form.

The `source_fan_out` result is the substantive finding. After the fix, the feature jumps from being the sixth-strongest single-feature discriminator to being the second-strongest, behind only `is_ntlm` (AUC 0.93). The shift makes physical sense: the corrected fan-out ratio captures the structural asymmetry of red-team source nodes. Across the 364,802 masked edges, the mean fan-out ratio is 0.974 for red-team source nodes and 0.695 for benign source nodes. Attackers behave like near-pure source nodes — almost all of their connectivity is outgoing, consistent with reconnaissance and lateral movement — while benign nodes have substantially more incoming connectivity. The methodology section already predicted that this asymmetry would be a strong signal; the bug had simply prevented that prediction from being tested.

The implication for the baseline comparison is that the corrected `source_fan_out` should slightly improve the unsupervised detectors when the pipeline is re-run, since the baselines will now receive a strong feature that the bug had been replacing with a redundant copy. We have not yet re-run the full pipeline to measure this effect; estimating from the single-feature AUC, the improvement is likely modest for Isolation Forest (which already extracts roughly this signal from `src_out_degree` and `dst_in_degree` jointly) and potentially larger for distance-based methods such as OCSVM that benefit more from explicitly-engineered ratios.

## The Information-Leakage Hazard

The diagnostic above is a useful description of the feature space, but it would be a methodological error to treat it as a feature-selection step. If we use the red-team labels to compute per-feature AUC, then choose the high-AUC subset, then train and evaluate the baseline detectors on the same labels, we have implicitly tuned the feature selection on the test set. The resulting AUC estimate is optimistically biased: the baselines have benefited from indirect knowledge of the very labels they are being evaluated against. This is the same class of methodological problem that the paper's `\subsection{Threshold Selection}` already acknowledges for the graph methods, where the threshold is auto-optimized against the red-team labels.

There are four principled ways to handle this. The first is to select features on independent grounds — domain knowledge or prior literature — and report the diagnostic above only as a descriptive characterization of the feature space, not as the basis for the choice. This is what the team's `SCORING_FEATURE_COLUMNS = ['edge_rarity', 'is_ntlm', 'is_network_logon', 'is_unusual_dst_port', 'protocol_rarity']` does: the five features are exactly those used in the heuristic scoring formula, which were chosen from domain knowledge about lateral movement, not from red-team AUC. This is the cleanest defense against a reviewer charge of leakage, even though one of the five (`is_unusual_dst_port`) turns out to be non-discriminative on this data.

The second option is to use the full feature set without selection. Passing all twelve features to the baselines makes no use of label information for feature choice and therefore introduces no leakage at the feature-selection stage. This is what the `extra_baselines` runner currently does (`scripts/run_extra_baselines.py`). The trade-off is that some features may be noise and can degrade distance-based methods (LOF and OCSVM) in high dimensions; we observed exactly this in the LOF-collapse finding documented in `report/Extra_Baselines_Full.md`.

The third option is to use a held-out validation split for feature selection. The data is partitioned into a feature-selection set and a final evaluation set with no overlap. Single-feature AUCs are computed on the validation portion, the top-K features are chosen, and the baseline detectors are then trained and evaluated only on the evaluation portion. With only 305 red-team edges to begin with, this split materially reduces statistical power on the evaluation set, but it produces an unbiased estimate of baseline performance under the selected features. This is the standard approach in supervised feature selection.

The fourth option is to use unsupervised feature selection — for instance, dropping features with variance below a threshold, or removing one of each pair of highly correlated features. The redundancy finding above (`edge_rarity` and `weight_norm`; `src_out_degree` and `source_fan_out`) supports an unsupervised reduction from twelve features to ten by removing exact-duplicates. This step uses no label information and is therefore leakage-free, and can be defended on the principle that mathematically redundant features add no information for any detector.

## Recommended Path: Held-Out Feature Selection Combined With Held-Out Threshold Selection

We adopt the third option as the chosen approach for the final paper. The deciding factor is a methodological synergy with work already on the paper's to-do list: the methodology section's `\subsection{Threshold Selection}` already commits us to moving threshold selection onto a held-out validation set, since the current pipeline auto-optimizes the percentile threshold against the same red-team labels that the metrics are computed on. Adding feature selection to the same held-out workflow piggybacks on the split we already need to construct, avoids introducing a separate split for a separate purpose, and lets a single section of the paper describe and defend a unified held-out protocol for both the threshold and the feature subset.

Concretely the protocol is as follows. The masked feature matrix (364,802 edges, 305 red-team) is partitioned by a stratified random split into a *calibration* half and an *evaluation* half, with the red-team prevalence preserved in each half. On the calibration half we compute the per-feature AUCs against the red-team labels and select features that exceed a fixed discrimination threshold (we adopt $\text{AUC} \geq 0.7$ on the calibration half, which yields approximately five to seven features depending on the random seed and is comparable in cardinality to the team's domain-knowledge subset). On the evaluation half — which the feature selector has never seen — we train each baseline detector on benign edges only, restricted to the selected features, and report AUC, recall, FPR, and F1. The same evaluation half also carries the threshold sweep for the graph-based methods once that work lands. With approximately 152 red-team edges in each half, the evaluation-half AUC has tolerable but reduced precision compared to a full-data evaluation; this is the cost of an unbiased estimate, and the paper should report it as such.

Within this held-out protocol we also adopt two label-free pre-processing steps that further harden the comparison.

First, we drop exact-duplicate features prior to selection and training. The diagnostic shows that `weight_norm` is mathematically identical to `edge_rarity` on this data, and `source_fan_out` is identical to `src_out_degree`. Including both members of either pair adds no information for any detector and can degrade distance-based detectors (LOF, OCSVM) by overweighting the duplicated direction. Removing one feature from each pair reduces the feature pool from twelve to ten and is justified on purely structural grounds with no reference to the labels.

Second, we apply a $\log(1+x)$ transformation to the heavy-tailed count features `src_out_degree` and `dst_in_degree` before standardization. These features have raw values that span several orders of magnitude (the diagnostic shows a mean benign `dst_in_degree` of 6,196 with a variance of order $10^7$), and the existing `StandardScaler` pipeline cannot rescue distance-based detectors from outlier domination. The log transformation is a standard, label-free preprocessing step that compresses the dynamic range while preserving rank order, and it benefits exactly those baselines that suffered most in our earlier results (LOF collapsed on the full feature matrix; OCSVM struggled throughout). Other transformations such as quantile or rank scaling were considered and rejected because they destroy the discriminative ordering on the binary indicators that carry most of the signal.

Two transformations we explicitly do not adopt: PCA, for the reasons in the prior section, and supervised feature scaling that uses red-team labels (e.g., per-feature weighting by training AUC), which would reintroduce exactly the leakage the held-out split is designed to eliminate.

## Diagnostic Artifacts

The diagnostic JSON used to generate the table above is at `results/20260504_183345/combined/feature_diagnostic.json`. The script that produced it is in `/tmp/feature_diag.py` (not committed; rerun manually if numbers need refreshing). The diagnostic is descriptive and is included in this report for transparency; it is **not** used to select features for the comparison reported elsewhere in the paper.

## Implementation Notes

The held-out protocol is being added to `scripts/run_extra_baselines.py` as an opt-in mode behind a `--holdout-frac` flag (default 0.5), with a companion `--min-auc` flag controlling the discrimination threshold for selection (default 0.7) and a `--log1p-degrees` flag (default on) controlling the unsupervised log transform of `src_out_degree` and `dst_in_degree`. Exact-duplicate removal is unconditional once the implementation lands. The runner remains independent of `src/baselines/shared_baselines.py` and the rest of the team's code; only the baseline-execution path (`run_baselines` and `run_extra_baselines`) is reused unchanged.

Numbers produced under the held-out protocol will differ from the existing twelve-feature full-data numbers reported in `report/Extra_Baselines_Full.md` for two reasons: the evaluation set is half the size, raising sampling noise, and the selected feature subset will be smaller and adapted to what the data shows is discriminative. The held-out numbers should be treated as the canonical paper-facing result once they are produced; the existing full-feature numbers will be retained as a supplementary "no feature selection" reference point.

## Status

This report covers three pieces of work, summarized here as of the current revision.

The **per-feature AUC diagnostic** is complete (`results/20260504_183345/combined/feature_diagnostic.json`). It established the ranking of the twelve raw features against the red-team labels and surfaced two structural findings: `is_unusual_dst_port` is essentially random on LANL despite being a domain-knowledge inclusion, and two pairs of features were exact duplicates due to a code bug.

The **duplicate-feature bug** is fixed on branch `ip/fix-feature-duplicates`. The fix is seven lines in `src/features/edge.py`, isolated from all other code, and has been verified to produce correct values on synthetic data. The empirical impact has been measured by recomputing per-feature AUC from cached graph data without re-running the full pipeline: `weight_norm` AUC is unchanged (still mirrors `edge_rarity` after sign-flip), and `source_fan_out` AUC improves from 0.78 to 0.91, making it the second-strongest single feature. A pull request will be opened separately from the feature-selection analysis PR.

The **held-out feature-selection protocol** is specified but not yet implemented. The runner additions (`--holdout-frac`, `--min-auc`, `--log1p-degrees`) and the unsupervised pre-processing steps (exact-duplicate removal, log-transform of degree counts) are described in the Recommendation section above. The implementation is the next concrete step; once it lands, the resulting numbers will be the paper-facing reference and will supersede the existing twelve-feature full-data numbers in `report/Extra_Baselines_Full.md`. The same calibration/evaluation split is intended to also carry the threshold-selection sweep currently parked in the paper's future-work list.

The team's existing `SCORING_FEATURE_COLUMNS = 5` convention on `main` remains defensible on its own terms and is preserved unchanged. Once the duplicate-feature fix is merged into `main`, that five-feature set should be reconsidered: it currently contains `is_unusual_dst_port` (AUC 0.51, ineffective) and excludes the corrected `source_fan_out` (AUC 0.91, the second-strongest feature). That reconsideration is a separate concern from this report and should be raised with the team.
