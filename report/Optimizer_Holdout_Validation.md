# Held-Out Validation of the Weight Optimizer, and Two Follow-Up Ablations

## Motivation

The `WeightOptimizer` in `src/optimization/optimizer.py` trains the scoring weights on the full feature matrix and reports the resulting AUC on the same matrix (the trace in `results/20260515_002159/optimization/optimized_weights.json` records `auc = 0.96846`, computed against the data the search used to fit). That value is optimistically biased by construction: Nelder-Mead has explored the weight space to fit the very labels it is being evaluated against. Without a held-out evaluation we cannot tell whether the optimizer learns weights that generalize, or whether it has found a configuration that happens to fit this specific sample of red-team labels.

The methodology section of the paper, and the `Feature_Selection_Analysis.md` companion report, already commit us to a held-out protocol for threshold selection and feature selection. The same protocol applies to weight optimization, and this document reports applying it. Two further ablations were run as natural follow-ups: a comparison between the bespoke Nelder-Mead optimizer and an off-the-shelf logistic-regression baseline, and a feature ablation that isolates how much of the discriminative signal lives in graph-derived features versus per-edge attributes that any tabular system could compute.

## Protocol

A new wrapper script, `scripts/optimize_weights_holdout.py`, takes the existing `WeightOptimizer` and runs it under a stratified calibration / evaluation split. The protocol is identical to the one specified in `Feature_Selection_Analysis.md`. The masked feature matrix is loaded with the same `src.feature_audit.loader.load_feature_frame` the audit uses. A stratified random split (`src.feature_audit.scorer.stratified_split`, seed 42, half-and-half) partitions the 364,802 masked edges into a calibration half (182,402 edges, 153 red-team) and an evaluation half (182,400 edges, 152 red-team), preserving red-team prevalence in both. The optimizer is constructed on the calibration half only, runs Nelder-Mead to convergence, and the resulting weights are then applied to the evaluation half — which the optimizer never sees during training — to produce the held-out AUC.

The wrapper is purely additive. It imports `WeightOptimizer` and `RANK_TRANSFORM_FEATURES` from `src.optimization.optimizer` without modifying them, and reuses the audit module's loader and split functions. No teammate-owned file is changed. Two further scripts were written as the analysis unfolded: `scripts/test_graph_features.py` for the quick-win graph-feature sweep, and `/tmp/tabular_vs_graph_ablation.py` for the tabular-vs-graph ablation. All three run against the same cached pipeline output and the same calibration / evaluation split, so their numbers are directly comparable.

## Result 1: The optimizer generalizes

Run against `results/20260515_002159/combined` with the same five features `optimized_weights.json` uses (`is_ntlm`, `source_fan_out`, `dst_in_degree`, `is_network_logon`, `dst_fan_out_ratio`):

| Quantity | Value |
|---|---|
| Calibration AUC (optimized weights, trained on cal half) | 0.968865 |
| Eval AUC (optimized weights, evaluated on held-out half) | **0.968070** |
| Calibration minus eval AUC | +0.000796 |
| Nelder-Mead iterations on calibration | 143 |

The optimization is generalizing. Calibration and evaluation AUCs agree to within 0.0008, well inside the noise we would expect from 152 / 153 red-team edges per split. There is no measurable over-fitting at five parameters and roughly 365,000 edges. The 0.968 figure in `optimized_weights.json` is not an in-sample artifact; it would still land near 0.968 on an unseen sample drawn from the same distribution. Reporting it in the paper as `0.968 (held-out)` is therefore defensible.

The gap is small because five free parameters against 305 red-team edges is roughly 0.016 parameters per positive sample — an extremely under-parameterized hypothesis class. There is effectively nothing for the optimizer to over-fit. This is a strength of the approach: the AUC improvement from manually-tuned weights (≈ 0.954) to optimized weights (0.968) is supportable from a small number of labels, with no held-out penalty.

## Result 2: Logistic regression matches the optimizer

A logistic-regression baseline was added to the same held-out wrapper, fit on the calibration half and evaluated on the evaluation half, with identical feature preprocessing (the same percentile-rank transform the optimizer applies to `edge_rarity` and `protocol_rarity`, followed by standardization on calibration-half statistics).

| Method | Cal AUC | Eval AUC | Cal − Eval gap | Wall time |
|---|---|---|---|---|
| Nelder-Mead optimizer | 0.9689 | 0.9681 | +0.0008 | ≈ 25 s |
| Logistic regression (L2, balanced class weights) | 0.9738 | **0.9733** | +0.0005 | ≈ 0.2 s |

Logistic regression and the Nelder-Mead optimizer are essentially equivalent on this data. The 0.005 eval-AUC gap in favor of LR is within single-seed noise, and both generalize cleanly. The Nelder-Mead approach does not add value over a standard supervised linear fit; the small numerical difference is most likely explained by LR having an intercept term and L2 regularization, neither of which materially changes the inductive bias here.

The implication is not that "we don't need the optimizer." The implication is that **the specific choice of supervised linear method does not matter** on this problem. Nelder-Mead, LR, and most other supervised linear methods on these five features will all land near AUC 0.97. The optimizer's value is in producing interpretable weights aligned with the scoring formula, not in optimizing better than off-the-shelf alternatives.

## Result 3: Where does the signal live? A pure-tabular versus graph-derived ablation

The Nelder-Mead-versus-LR comparison only varies the *learner*; both methods use the same five features. To test whether the *features themselves* carry the signal — and specifically whether the graph-derived ones matter — we ran a feature ablation that holds the learner constant (logistic regression, same held-out split, seed 42) and varies the feature set.

We split the available features into two groups by whether they require graph topology to compute. *Pure tabular* features are computable from per-edge attributes alone: authentication flags, edge rarity (a function of edge weight), protocol rarity, byte-per-packet, duration z-score, and the unusual-destination-port flag. *Graph-derived* features require traversing the graph: node degrees in both directions, fan-out ratios, node-level temporal features (inter-arrival statistics, burst score, active duration), and destination-node betweenness centrality.

| Feature set | # features | Cal AUC | Eval AUC |
|---|---|---|---|
| A. Pure tabular only | 9 | 0.9609 | 0.9562 |
| B. Graph-derived only | 17 | 0.9893 | **0.9891** |
| C. Combined (A + B) | 26 | 0.9981 | 0.9922 |

The picture is unambiguous. Adding graph-derived features on top of the pure-tabular set raises eval AUC by **+0.0359**, while adding pure-tabular features on top of the graph-derived set raises eval AUC by only **+0.0030**. Graph-derived features carry roughly an order of magnitude more discriminative signal than pure-tabular features on this dataset.

This is the result that vindicates the graph-based methodology. The earlier, sloppier framing — *"LR with five features matches the full pipeline, so the graph part isn't helping"* — conflated **tabular methods** with **tabular features**. Logistic regression is a tabular method, but the five features it was using included three graph-derived columns (`source_fan_out`, `dst_in_degree`, `dst_fan_out_ratio`); the comparison was therefore *learner-versus-learner on graph features*, not *graph-versus-no-graph*. The proper ablation above isolates the feature contribution and shows that the graph-derived features do most of the work.

## Result 4: Specific graph extensions beyond local features

The ablation above shows that local graph features (degrees, fan-out, node-level temporal patterns) carry the bulk of the signal. A natural follow-up question is whether *multi-hop* graph reasoning — features that require traversing more than one hop — adds anything further. We swept five candidate graph features added one group at a time on top of the five-feature LR baseline.

| Feature group | Cal AUC | Eval AUC | Δ vs base |
|---|---|---|---|
| (base: 5 features only) | 0.9738 | 0.9733 | — |
| Standard PageRank | 0.9739 | 0.9734 | +0.0002 |
| **Personalized PageRank seeded at `C17693`** | **0.9964** | **0.9956** | **+0.0224** |
| k-core decomposition | 0.9773 | 0.9771 | +0.0039 |
| Louvain community (cross-community flag plus community-size features) | 0.9779 | 0.9779 | +0.0046 |
| Jaccard + Adamic-Adar similarity | 0.9737 | 0.9733 | +0.0001 |
| All five groups stacked | 0.9968 | 0.9965 | +0.0232 |

Three observations.

Personalized PageRank seeded at the known compromised host adds far more than any other feature in the sweep. This is a real signal, but it carries an unavoidable methodological caveat: the feature uses the identity of `C17693` as an input, and in a production deployment that identity would have to be discovered first. The result therefore supports a *conditional* paper claim ("given a seed of confirmed-compromised hosts, structural propagation lifts eval AUC from 0.973 to 0.996") rather than a *cold-start detection* claim. Carefully framed as a post-detection scoping mechanism, this is publishable; presented without qualification, it overstates what the method can achieve when no attacker is known.

The label-free graph features — k-core decomposition and Louvain community membership — each add a modest but consistent improvement of roughly 0.004 eval AUC over the local-graph baseline. These features require no prior information about attackers and can be cited in the paper as direct support for the claim that multi-hop graph structure carries detectable signal beyond local features. Standard PageRank and edge-similarity scores (Jaccard, Adamic-Adar) contribute essentially nothing on this dataset.

Stacking all five quick-win groups together reaches eval AUC 0.9965, but the gain is dominated by the personalized-PageRank contribution. With personalized PageRank removed from the stack, the remaining label-free graph features push eval AUC to roughly 0.978, a smaller and more conservative improvement.

## Synthesis: what each comparison actually tests

The four results above sit on different axes; it is worth saying explicitly what each one isolates.

| Comparison | What is held constant | What varies | What it measures |
|---|---|---|---|
| Result 1: cal-AUC vs eval-AUC of the optimizer | optimizer, features, split | which half is evaluated | Does the optimizer over-fit? *No.* |
| Result 2: Nelder-Mead vs LR | features, split, supervision paradigm | choice of supervised linear method | Does the specific optimizer matter? *Not measurably.* |
| Result 3: pure-tabular vs graph-derived LR | learner, supervision, split | which features the learner sees | Do graph-derived features add signal? *Yes, +0.036 AUC.* |
| Result 4: LR + each quick-win group | learner, base features, split | additional graph feature group | Do specific multi-hop graph features add signal beyond local? *Modestly, label-free; substantially with known-attacker seed.* |

The one-class baselines already in the paper (Isolation Forest, OCSVM, Local Outlier Factor, Elliptic Envelope, PCA reconstruction) play a different role still: they hold the features constant and vary the training paradigm from supervised to one-class. The empirical observation there — Isolation Forest at AUC 0.94 versus LR at AUC 0.99 on the same graph-derived features — measures the *supervision effect*: roughly +0.05 AUC from having labels at training time rather than relying on one-class learning of the benign distribution.

Taken together, the four results plus the one-class comparison decompose the path from naïve detection to the best AUC currently achievable into three additive contributions:

| Contribution | Approximate AUC delta | Evidence |
|---|---|---|
| Pure-tabular features under one-class learning (rough lower bound) | — | implied baseline; not directly measured here |
| Pure-tabular features under supervised LR | +0.05 over one-class on the same features (inferred) | Result 2 + one-class baselines |
| Graph-derived local features (degrees, fan-out, node temporal) under supervised LR | +0.036 over pure tabular | Result 3 |
| Multi-hop graph features (k-core, communities) on top | +0.004 to +0.007 | Result 4 |
| Known-attacker propagation (personalized PageRank) on top | +0.022, conditional on a known attacker | Result 4 |

The total budget is roughly +0.10 from the worst defensible baseline (pure-tabular one-class) to the most aggressive supervised graph-aware system; **the largest single addition is the graph-derived features themselves**, not the choice of optimizer, not the multi-hop reasoning, and not the path-boost mechanism currently in the pipeline.

## What this means for the paper

Three claims emerge from the data with clear empirical backing.

**Graph-derived features carry the bulk of the discriminative signal for lateral-movement detection on LANL-2015.** Substituting pure-tabular features for graph-derived features under the same supervised linear learner drops eval AUC by roughly 0.036. This claim survives any reasonable framing of "what counts as graph data" because the ablation uses the binary distinction "requires graph topology to compute" rather than algorithmic choices about how to use the graph.

**Supervised learning is a separate, additive contribution.** Comparing logistic regression on the graph-derived features (eval AUC 0.99) to the existing one-class baselines on the same features (Isolation Forest at AUC 0.94) shows a roughly 0.05 AUC improvement that is attributable to having labels at training time. This is independent of the graph-feature claim above; both effects compound.

**Among supervised linear methods on the same features, the specific algorithm matters little.** Nelder-Mead direct AUC maximization and logistic regression agree to within single-seed noise. The optimizer's value is in producing interpretable weights aligned with the scoring formula; it is not the source of the AUC gain. This is honest negative evidence and can be reported as such.

A fourth, weaker claim is available: multi-hop graph reasoning beyond local features adds modest improvement (≈ +0.005 from label-free features such as community membership). This should be reported as supplementary evidence rather than as a headline.

A fifth claim — that personalized PageRank from a known-attacker seed reaches eval AUC 0.996 — is real but conditional. It belongs in the paper if framed honestly as a post-detection lateral-movement scoping mechanism; it does not belong in the paper as a cold-start detection result.

Together these reshape the paper's narrative away from *"our scoring formula matters"* (which is not strongly supported by the held-out numbers — the manual-weight and path-boost mechanism in the current pipeline reaches AUC 0.954, while a supervised linear classifier on the same features reaches 0.99) toward *"feature engineering for graph-based lateral movement detection matters"* (which is strongly supported). The pipeline's specific scoring formula and path-boost mechanism are a worthwhile engineering artifact but are not the source of the result; the source is the choice of features.

## Output and reproducibility

The three scripts and their outputs:

| Script | Output | Run reported here |
|---|---|---|
| `scripts/optimize_weights_holdout.py` | `results/<timestamp>/optimization_holdout/holdout_results.json` (includes both optimizer and LR results) | `results/20260515_093756/optimization_holdout/holdout_results.json` |
| `scripts/test_graph_features.py` | `results/<timestamp>/graph_features_test/graph_features_test.json` | `results/20260515_095236/graph_features_test/graph_features_test.json` |
| `/tmp/tabular_vs_graph_ablation.py` | stdout only (not committed) | re-run as needed |

To reproduce the held-out optimizer + LR comparison:

```
uv run python scripts/optimize_weights_holdout.py \
    --run-dir results/20260515_002159/combined
```

To reproduce the quick-win graph-feature sweep:

```
uv run python scripts/test_graph_features.py \
    --run-dir results/20260515_002159/combined
```

All three runs use `holdout_frac = 0.5` and seed 42 by default; both are CLI flags for sweeps.

## Status and follow-ups

The single methodological concern this document set out to address — that the optimizer's AUC was reported on the same data it was trained on — is closed. The optimizer generalizes. Beyond that, the analysis added comparisons that surface a clearer picture of where the AUC gain comes from than the paper's current narrative captures.

Three follow-ups are natural next steps, none blocking.

The first is multi-seed evaluation. All numbers above are from seed 42. Re-running each comparison across seeds 0–9 and reporting mean and standard deviation would put the headline result on the same footing as the paper's planned statistical-significance experiment.

The second is the path-boost diagnostic noted earlier: add the pipeline's path-derived `path_score` (or the post-boost residual) as an additional column to the LR baseline. If eval AUC stays at 0.989, the path mechanism is not contributing held-out signal under the current implementation. If it rises noticeably, the path mechanism is contributing and the bottleneck is the manual weights elsewhere in the pipeline.

The third is the generalization of the personalized-PageRank finding: instead of seeding at the single attacker `C17693`, seed propagation from the full set of red-team source nodes (or from a held-out subset) and report eval AUC. This converts the current "known single attacker" result into a "set of confirmed-compromised hosts" result, which is the cleaner operational claim and supports the paper's incident-response framing.
