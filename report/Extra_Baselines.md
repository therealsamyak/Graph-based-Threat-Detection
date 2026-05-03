# Extending the Baseline Comparison: Five Tabular Anomaly Detectors on LANL-2015

## Motivation

The current methodology document (`report/Submission.md`) identifies the most pressing weakness of our experimental setup: the graph-based methods are evaluated on LANL-2015 while the tabular baselines (One-Class SVM and Isolation Forest) are evaluated on DAPT2020, which makes the apparent advantage of the graph approach unfalsifiable. Experiment #1 of the planned work — *Cross-Dataset Validation and Baseline Alignment* — calls for re-running the tabular baselines on LANL-2015 features so that every method is judged against the same ground truth. This document reports the first half of that experiment: tabular ML baselines applied to LANL-2015 edge features, evaluated against the same red-team labels used by the graph-based methods. The second half (the graph method applied to DAPT2020) remains future work.

In addition to the two baselines listed in the original methodology, we extend the baseline pool with three further unsupervised detectors — Local Outlier Factor, Elliptic Envelope, and PCA reconstruction error — to broaden the comparison and pre-empt a reviewer objection that only two baselines were considered. All five baselines operate on the same twelve-dimensional feature vector extracted per edge from the LANL-2015 combined graph.

## Methodology

### Data and Feature Matrix

The comparison reuses the cached outputs of run `20260502_165755`, which is the most recent full-pipeline run on LANL-2015. The relevant artifacts are `results/20260502_165755/combined/edge_features.csv` (one row per edge, containing the per-edge features computed in `src/features.py`) and `results/20260502_165755/redteam/redteam_pairs.json` (the 308 ground-truth red-team source-destination pairs). Running the baselines against these cached files avoids re-executing the three-hour pipeline and isolates the question being asked: *given the same per-edge features and ground-truth labels, how do tabular anomaly detectors compare to the graph-based scoring formulas?*

We follow the same masking convention used by `src/baselines/lanl_baselines.py`: self-loops and user-to-user edges are excluded, since these carry no lateral-movement signal under our methodology. After masking, the feature matrix contains 364,802 edges, of which 305 belong to red-team source-destination pairs. The twelve features used are: `edge_rarity`, `src_out_degree`, `dst_in_degree`, `is_ntlm`, `is_network_logon`, `is_success_auth`, `source_fan_out`, `weight_norm`, `is_unusual_dst_port`, `protocol_rarity`, `byte_per_packet`, and `duration_zscore`. Missing values are replaced with zero, and all features are standardized to zero mean and unit variance using a `StandardScaler` fit on the benign (non-red-team) subset, exactly as in `shared_baselines.py`.

### Sub-sampling

One-Class SVM with an RBF kernel is O(n²) in the number of training samples and does not finish within reasonable wall-clock time on the full 364,802-edge feature matrix; this is the same scaling issue that prevents the existing pipeline from producing LANL-2015 OCSVM rows in `metrics.csv`. To allow a fair comparison across all five methods on identical data, we sub-sample the benign edges to 100,000 and retain all 305 red-team edges, producing a 100,305-edge evaluation matrix. The random seed is fixed at 42 for reproducibility. We acknowledge this introduces a small evaluation bias relative to the full graph-based runs; however, because all five baselines see the same sub-sampled matrix, the *relative* ordering of baselines is unaffected, and AUC is not strongly sensitive to benign-class size at this scale.

### Detection Methods

The two baselines from the original methodology, **One-Class SVM** (RBF kernel, gamma="scale", nu=0.1) and **Isolation Forest** (100 estimators, contamination=0.05, random_state=42), are unchanged from `src/baselines/shared_baselines.py`. The three additional baselines are implemented in a new isolated module `src/baselines/extra_baselines.py`, which mirrors the schema and concurrency pattern of `shared_baselines.py` so that results can be concatenated cleanly without touching shared code paths.

**Local Outlier Factor (LOF)** scores each point by comparing the local density of its k-nearest-neighbor neighborhood to the densities of its neighbors. Points in sparse regions relative to their neighbors receive higher anomaly scores. We use `sklearn.neighbors.LocalOutlierFactor` with `n_neighbors=20`, `contamination=0.05`, and `novelty=True`, which fits on the benign training set and exposes a `decision_function` for ROC computation.

**Elliptic Envelope** fits a robust multivariate Gaussian to the benign features using a Minimum Covariance Determinant estimator and flags points whose Mahalanobis distance from the fit exceeds a contamination-controlled threshold. We use `sklearn.covariance.EllipticEnvelope` with `contamination=0.05` and `random_state=42`.

**PCA reconstruction error** projects each point onto the top-K principal components fit on the benign data, reconstructs the point in the original feature space, and uses the squared L2 reconstruction error as the anomaly score. We use `sklearn.decomposition.PCA` with `n_components=5` and a contamination threshold of 0.05 applied to the empirical error distribution.

### Evaluation Protocol

Each method produces a continuous anomaly score and a binary prediction (anomaly versus benign) on the full 100,305-edge evaluation set. We compute five metrics: AUC (area under the ROC curve, threshold-independent, computed against the continuous score), F1, recall, precision, and false-positive rate (computed against the binary prediction). All metrics are computed in *edge space* — that is, every edge counts as a separate evaluation sample. This differs from the graph methods reported in `Submission.md`, which evaluate F1, recall, and FPR in *pair space* (deduplicated source-destination pairs). AUC is comparable across both spaces because it is a function of score ranks rather than thresholded pair identities; the threshold-dependent metrics are not directly comparable and are reported here for internal calibration only.

## Results

The five baselines were evaluated on the 100,305-edge sub-sampled feature matrix; total runtime was approximately 3.5 minutes (195.6 seconds for OCSVM + Isolation Forest in parallel, 21.1 seconds for LOF + Elliptic Envelope + PCA in parallel). The complete results, sorted by AUC in descending order:

| Method | AUC | F1 (edge) | Recall (edge) | Precision (edge) | FPR (edge) |
|---|---|---|---|---|---|
| Isolation Forest | 0.9449 | 0.0841 | 0.7639 | 0.0445 | 0.0500 |
| Local Outlier Factor | 0.8877 | 0.0761 | 0.6098 | 0.0406 | 0.0440 |
| Elliptic Envelope | 0.7727 | 0.0000 | 0.0000 | 0.0000 | 0.0500 |
| One-Class SVM | 0.7002 | 0.0271 | 0.4689 | 0.0140 | 0.1010 |
| PCA Reconstruction | 0.6683 | 0.0034 | 0.0295 | 0.0018 | 0.0500 |

For reference, the graph-based methods on the same run produced (in pair space, from `metrics.csv`):

| Method | AUC | F1 (pair) | Recall (pair) | FPR (pair) |
|---|---|---|---|---|
| combined (graph) | 0.9544 | 0.0387 | 0.6623 | 0.0196 |
| auth_only (graph) | 0.9508 | 0.0364 | 0.7468 | 0.0296 |
| flow_only (graph) | 0.5785 | 0.0019 | 0.0130 | 0.0297 |

## Discussion

### Headline: Isolation Forest is a strong baseline, not a weak one

Isolation Forest reaches AUC 0.9449 on the LANL-2015 features — only 0.0095 below the combined graph method (0.9544) and within the same noise band as auth-only (0.9508). This is a stronger baseline than the original DAPT2020-only comparison suggested, and the paper should acknowledge it explicitly rather than presenting the graph method as having a wide margin over tabular learning. The honest framing is that the graph method achieves slightly better discrimination at materially lower false-positive rate (FPR 0.0196 in pair space versus 0.0500 in edge space for IF at the same operating point); the *AUC gap is small, the operational gap is meaningful*. This is a more defensible claim than a blanket "graph beats tabular," and it is consistent with what the data show.

### Local Outlier Factor is a useful corroborating baseline

LOF reaches AUC 0.8877, materially below Isolation Forest but well above the remaining three methods. Because LOF is density-based while Isolation Forest is partition-based, the fact that both top the table corroborates the underlying signal: the LANL-2015 edge features genuinely separate red-team from benign edges, and the result is not an artifact of any one detector's inductive bias. The paper benefits from including LOF in the comparison table for exactly this reason.

### Elliptic Envelope, OCSVM, and PCA reconstruction underperform

Elliptic Envelope produces a respectable AUC (0.7727) but zero F1 because its 0.05-contamination decision boundary, calibrated on the robust covariance fit, does not place any of its 5,015 flagged edges among the 305 red-team edges. This is a calibration failure rather than a discrimination failure — the rank ordering carries some signal, but the chosen threshold does not exploit it. Reporting AUC alone rescues the method's reputation; the F1 column is misleading.

One-Class SVM reaches AUC 0.7002, well below Isolation Forest. The result is consistent with the existing observation that OCSVM is the weakest of the standard tabular detectors on this kind of network event data, and it underperforms despite being computationally the most expensive of the five. The paper should retain OCSVM in the comparison for canonicity but should not treat it as the strongest baseline.

PCA reconstruction error reaches AUC 0.6683, the weakest of the five. This is consistent with the underlying feature space being dominated by binary indicators (`is_ntlm`, `is_network_logon`, `is_success_auth`, `is_unusual_dst_port`) for which PCA reconstruction is a poor anomaly signal — the reconstruction error of a binary feature is bounded and does not amplify rare combinations.

### Implications for the methodology document

The current draft of `Submission.md` lists OCSVM and Isolation Forest as the only baselines and reports them only on DAPT2020. Once Experiment #1 is finalized, we recommend three changes to the methodology section:

The Baseline Methods subsection should be expanded to describe all five methods (OCSVM, Isolation Forest, LOF, Elliptic Envelope, PCA reconstruction). LOF should be highlighted as a density-based corroborator of the partition-based Isolation Forest result.

The Preliminary Results section should add a unified comparison table showing all eight methods (three graph variants plus five tabular baselines) on LANL-2015, with the explicit caveat that tabular F1/recall/FPR are computed in edge space while graph F1/recall/FPR are in pair space, but AUC is comparable across both. The honest comparison places combined (0.9544) and Isolation Forest (0.9449) within striking distance of each other, with auth-only (0.9508) in between.

The What Remains To Be Done section should note that Experiment #1's first half is complete and that the remaining work is the symmetric direction: applying the graph-based scoring methodology to DAPT2020 flow records.

## Reproducibility

The code added by this experiment is contained in two new files: `src/baselines/extra_baselines.py` (the LOF, Elliptic Envelope, and PCA-reconstruction implementations, mirroring the schema of `shared_baselines.py`) and `scripts/run_extra_baselines.py` (the standalone runner that loads cached features, applies the LANL mask, optionally sub-samples benign edges, and writes JSON and Markdown output). No existing files were modified. The full results JSON for this report is at `results/20260502_165755/combined/extra_baselines_100k.json`, and the auto-generated raw table is at `results/20260502_165755/combined/extra_baselines_100k.md`. The runner can be invoked as:

```
uv run python scripts/run_extra_baselines.py results/20260502_165755/combined --sample-size 100000 --out-suffix extra_baselines_100k
```

## Limitations and Future Work

The most important limitation is the sub-sampling of benign edges to 100,000. While AUC is robust to this choice, threshold-dependent metrics shift because the prevalence of red-team edges in the evaluation set is artificially elevated (305 / 100,305 = 0.30% rather than 305 / 364,802 = 0.08%). Once the OCSVM scaling issue is resolved — either by switching to a linear kernel, sub-sampling within OCSVM only, or replacing OCSVM with a Nyström-approximated SVM — we should re-run all five methods on the full 364,802-edge matrix and confirm the ordering is unchanged.

The second limitation is that the comparison is one-directional. Experiment #1 of the methodology requires both *baselines on LANL-2015* (this report) and *graph methods on DAPT2020* (still future work). Only the bidirectional comparison rules out the alternative explanation that the graph approach's apparent advantage is dataset-specific.

The third limitation is hyperparameter neutrality. We used reasonable defaults for each method (`n_neighbors=20` for LOF, `n_components=5` for PCA, `contamination=0.05` throughout) without per-method tuning. A small grid search per method, reported in an appendix, would harden the comparison against the objection that the baselines were under-tuned relative to the manually-weighted graph scoring formulas.
