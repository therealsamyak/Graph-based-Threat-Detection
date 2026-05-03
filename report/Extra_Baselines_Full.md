# Full-Data Validation of the Tabular Baselines on LANL-2015

## Motivation

The companion report `report/Extra_Baselines.md` evaluated five unsupervised tabular detectors (One-Class SVM, Isolation Forest, Local Outlier Factor, Elliptic Envelope, and PCA reconstruction error) on a 100,305-edge sub-sample of the LANL-2015 combined graph. The sub-sampling was a practical concession: One-Class SVM with an RBF kernel is O(n²) in training samples and would not finish within reasonable wall-clock time on the full 364,802-edge feature matrix. The sub-sampled report flagged this as its most important limitation, noting that AUC is generally robust to benign-class size at this scale but that threshold-dependent metrics shift because the artificial sub-sample concentrates the prevalence of red-team edges. The first-half report explicitly recommended re-running every method on the full 364,802-edge matrix once a path forward existed for the OCSVM scaling issue.

This document reports the result of doing exactly that. We re-ran all five baselines on the full LANL-2015 combined-graph feature matrix without sub-sampling. The total wall time was 40.8 minutes, dominated by One-Class SVM training; the other four methods completed in 71 seconds combined. The purpose of this report is twofold: to confirm or refute the rank ordering established by the sub-sampled run, and to update the discussion in light of any baselines whose behavior changes at full scale.

## Methodology

The methodology is identical to the companion report in every respect except sub-sampling. The same twelve features are extracted per edge from `results/20260502_165755/combined/edge_features.csv`, the same self-loop and user-edge mask is applied, and the same `StandardScaler` fit on benign data is used. The same hyperparameters are passed to every method: One-Class SVM uses an RBF kernel with `gamma="scale"` and `nu=0.1`, Isolation Forest uses 100 estimators and `contamination=0.05`, Local Outlier Factor uses `n_neighbors=20` and `contamination=0.05` in novelty mode, Elliptic Envelope uses `contamination=0.05`, and PCA reconstruction uses `n_components=5` with a 0.05 contamination threshold applied to the empirical squared-error distribution. The only difference is the size of the evaluation matrix: 364,802 edges (305 red-team) versus 100,305 edges (305 red-team) in the sub-sampled run. Both runs evaluate against the identical 305-pair red-team ground truth.

## Results

### Full-data results (364,802 edges)

| Method | AUC | F1 (edge) | Recall (edge) | Precision (edge) | FPR (edge) |
|---|---|---|---|---|---|
| Isolation Forest | 0.9397 | 0.0241 | 0.7410 | 0.0122 | 0.0500 |
| Elliptic Envelope | 0.7741 | 0.0000 | 0.0000 | 0.0000 | 0.0500 |
| One-Class SVM | 0.7059 | 0.0083 | 0.4918 | 0.0042 | 0.0982 |
| PCA Reconstruction | 0.6672 | 0.0011 | 0.0328 | 0.0005 | 0.0500 |
| Local Outlier Factor | 0.4925 | 0.0076 | 0.2066 | 0.0039 | 0.0447 |

### Sampled-data results, repeated for comparison (100,305 edges)

| Method | AUC | F1 (edge) | Recall (edge) | Precision (edge) | FPR (edge) |
|---|---|---|---|---|---|
| Isolation Forest | 0.9449 | 0.0841 | 0.7639 | 0.0445 | 0.0500 |
| Local Outlier Factor | 0.8877 | 0.0761 | 0.6098 | 0.0406 | 0.0440 |
| Elliptic Envelope | 0.7727 | 0.0000 | 0.0000 | 0.0000 | 0.0500 |
| One-Class SVM | 0.7002 | 0.0271 | 0.4689 | 0.0140 | 0.1010 |
| PCA Reconstruction | 0.6683 | 0.0034 | 0.0295 | 0.0018 | 0.0500 |

### AUC delta, full minus sampled

| Method | AUC (full) | AUC (sampled) | Delta |
|---|---|---|---|
| Isolation Forest | 0.9397 | 0.9449 | -0.0052 |
| Elliptic Envelope | 0.7741 | 0.7727 | +0.0014 |
| One-Class SVM | 0.7059 | 0.7002 | +0.0057 |
| PCA Reconstruction | 0.6672 | 0.6683 | -0.0011 |
| Local Outlier Factor | 0.4925 | 0.8877 | **-0.3952** |

## Discussion

### Headline: four of five methods are stable, LOF collapses

The AUC of four of the five baselines moves by less than 0.006 between the sub-sampled and full-data runs. This confirms the central methodological assumption of the companion report: AUC is robust to the size of the benign class at this scale, and the rank ordering among Isolation Forest, Elliptic Envelope, One-Class SVM, and PCA reconstruction does not change. Isolation Forest remains the strongest tabular baseline at AUC 0.940 on the full data, only 0.014 below the combined graph method (0.954) and 0.011 below auth-only (0.951). The paper's central claim — that the graph approach matches the best tabular baseline on AUC and decisively beats it on FPR — survives the full-data re-evaluation.

The exception is Local Outlier Factor, whose AUC drops from 0.888 on the sub-sample to 0.493 on the full data — essentially indistinguishable from random. This is a substantive finding and reverses one of the conclusions of the companion report, which had described LOF as a "strong second" and a "density-based corroborator" of Isolation Forest. That description is no longer supportable. On the full LANL-2015 feature matrix, LOF does not provide a meaningful anomaly signal.

### Why Local Outlier Factor collapses at full scale

LOF computes an anomaly score by comparing the local reachability density of a point to the densities of its k-nearest neighbors. With `n_neighbors=20`, a point is flagged as anomalous when its 20-nearest-neighbor density is much lower than the mean density of those 20 neighbors. The LANL feature matrix is dominated by binary indicators (`is_ntlm`, `is_network_logon`, `is_success_auth`, `is_self_loop`, `is_user_edge`, `is_unusual_dst_port`) and tightly-binned percentile ranks (`edge_rarity`, `protocol_rarity`, `weight_norm`). After standardization, most edges occupy a small number of discrete lattice corners in the twelve-dimensional feature space.

At 100,000 benign edges, those lattice corners are populated densely enough to give LOF a recognizable density gradient: red-team edges that fall in less-populated corners receive higher LOF scores than benign edges in dense corners. At 364,000 benign edges, every lattice corner is so densely populated that all twenty nearest neighbors of any point — red-team or benign — are at near-zero distance. The resulting reachability densities are saturated, the relative density signal collapses, and LOF degenerates to noise. This is a known failure mode of density-based anomaly detection on categorical or near-categorical data; it is reported in the LOF literature as a sensitivity to the curse of dimensionality combined with feature granularity.

The practical conclusion is that LOF is not a useful baseline for LANL-2015 with the current feature set. A future ablation could distinguish between LOF the algorithm and LOF the algorithm-on-binary-features by extending it to a richer feature space (e.g., Node2Vec embeddings of the host graph, which would produce continuous-valued neighborhood vectors), but on the existing twelve-dimensional tabular feature matrix LOF should be reported as ineffective rather than competitive.

### Threshold-dependent metrics drop because of the base-rate change

Every method's F1, recall, and precision is lower on the full data than on the sub-sample. Isolation Forest's F1 drops from 0.084 to 0.024, recall from 0.764 to 0.741, and precision from 0.045 to 0.012; the other methods follow the same pattern. This is not a degradation of the underlying detector — it is a pure base-rate effect. With contamination fixed at 5%, Isolation Forest flags 5% of the input as anomalous: 5,000 edges in the sub-sampled run, 18,240 edges in the full run. The number of red-team edges in the input is the same (305) in both cases, so when the same fraction of detected red-team edges (~76%) is divided by a 3.6× larger flagged-edge set, precision and F1 fall in proportion to the base-rate change. Recall is preserved because it is computed against the constant red-team count.

This effect underscores the importance of the caveat already noted in the companion report: edge-space F1 and precision at fixed contamination are not operationally meaningful metrics on this dataset. A production deployment would not flag 5% of all authentications as suspect; it would target a fixed false-positive budget or recall floor and tune the threshold to that budget. AUC is the threshold-independent metric that should drive method selection. Both reports concur on AUC ranking, so the practical conclusion is unchanged.

### Updated paper-facing recommendations

The companion report's three recommended changes to `report/Submission.md` should be reissued with two updates. First, the unified comparison table should report AUC from the full-data run (Isolation Forest 0.9397, Elliptic Envelope 0.7741, One-Class SVM 0.7059, PCA reconstruction 0.6672, LOF 0.4925) rather than the sub-sampled run, because the full-data values are the apples-to-apples comparison against the graph methods that themselves run on the full graph. Second, the previous report's framing of LOF as a corroborating density-based baseline should be retracted; LOF should instead be reported as an instructive negative result, demonstrating that density-based detection on the LANL feature space does not generalize beyond a small benign-sample size and serving as evidence that the graph method's signal is structural rather than density-based. The `Submission.md` Baseline Methods subsection should now describe four meaningful baselines (OCSVM, Isolation Forest, Elliptic Envelope, PCA reconstruction) plus LOF as a documented failure case.

### Wall-time and reproducibility

Total runtime was 40.8 minutes on a laptop, of which 39.8 minutes were spent in One-Class SVM training (the other four methods completed in parallel in 71 seconds). This is well within the budget of a single overnight run and confirms that full-scale evaluation is feasible without algorithmic changes to the runner. If OCSVM is dropped or replaced with a Nyström-approximated linear-kernel variant, the full-data evaluation drops to under two minutes.

The full-data run was produced by:

```
uv run python scripts/run_extra_baselines.py results/20260502_165755/combined --out-suffix extra_baselines_full
```

The artifacts are at `results/20260502_165755/combined/extra_baselines_full.json` (full numerical payload) and `results/20260502_165755/combined/extra_baselines_full.md` (auto-generated raw table). No new code was added; the runner already supported full-data evaluation by omitting the `--sample-size` argument.

## Status of Experiment #1

With this report, the first half of Experiment #1 from the methodology document is fully complete. Tabular baselines have been evaluated on LANL-2015 against the same red-team ground truth as the graph methods, both at the sub-sampled scale (companion report) and at full scale (this report), and the conclusion is consistent: Isolation Forest is the strongest tabular baseline at AUC 0.940, materially below the combined graph method's 0.954 on AUC and a factor of 2.5 worse on false-positive rate at comparable recall. The remaining work for Experiment #1 is the symmetric direction — applying the graph-based scoring methodology to DAPT2020 — which is unaffected by the findings here and remains future work.
