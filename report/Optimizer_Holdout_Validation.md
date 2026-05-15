# Held-Out Validation of the Weight Optimizer

## Motivation

The `WeightOptimizer` in `src/optimization/optimizer.py` trains the scoring weights on the full feature matrix and reports the resulting AUC on that same matrix (see the trace in `results/20260515_002159/optimization/optimized_weights.json`, where `auc = 0.96846` is the calibration-set AUC). That value is optimistically biased by construction: Nelder-Mead has searched the weight space to fit the very labels it is being evaluated against. Without a held-out evaluation we cannot distinguish "the weights generalize" from "the optimizer found a configuration that happens to fit this specific sample of red-team labels."

The methodology section of the paper (and the `Feature_Selection_Analysis.md` companion report) already commits us to a held-out protocol for threshold selection and feature selection. The same protocol applies to weight optimization. This document reports the result of applying it.

## What was done

A new wrapper script, `scripts/optimize_weights_holdout.py`, takes the same `WeightOptimizer` and runs it under a stratified calibration / evaluation split. Concretely the protocol is identical to the one described in `Feature_Selection_Analysis.md`:

1. Load the masked feature matrix using `src.feature_audit.loader.load_feature_frame` (the same loader the audit uses).
2. Stratified 50/50 split on the labels using `src.feature_audit.scorer.stratified_split`, preserving red-team prevalence in both halves.
3. Construct a `WeightOptimizer` on the calibration half only. Run Nelder-Mead to convergence. The optimizer never sees eval-half rows during training.
4. Apply the optimized weights to the eval half and compute the held-out AUC.
5. Report calibration AUC, eval AUC, the gap, and an equal-weights baseline.

The wrapper is purely additive. It imports `WeightOptimizer` and `RANK_TRANSFORM_FEATURES` from `src.optimization.optimizer` without modifying them; no other teammate-owned file is changed.

## Results

Run against `results/20260515_002159/combined` (the post-bug-fix pipeline output your draft was already using), with the same five features hard-coded in `optimized_weights.json` (`is_ntlm`, `source_fan_out`, `dst_in_degree`, `is_network_logon`, `dst_fan_out_ratio`) and `holdout_frac = 0.5`, seed 42:

| Quantity | Value |
|---|---|
| Calibration AUC (optimized weights, trained on cal half) | 0.968865 |
| Eval AUC (optimized weights, evaluated on held-out half) | **0.968070** |
| Full-set AUC (optimized weights, reference) | 0.968463 |
| Equal-weights baseline AUC | 0.197872 (most features anti-correlated with the default-positive sign; not a meaningful comparison) |
| Calibration minus eval AUC | +0.000796 |
| Nelder-Mead iterations | 207 on full / 143 on calibration half |

The optimization is generalizing. The calibration and eval AUCs agree to within 0.0008, well inside the noise we would expect from the 152 / 153 red-team edges in each split. There is no measurable over-fitting at five parameters and ~365 k edges. The number you reported in `optimized_weights.json` is not an artifact of in-sample evaluation; it would still land at approximately 0.968 on an unseen sample of the same distribution.

## Why the gap is so small

Five free parameters against 305 red-team edges is roughly 0.016 parameters per positive sample. The hypothesis class is small enough that there is effectively nothing for the optimizer to over-fit. This is a strength of the approach: the AUC improvement from the manually-tuned weights (~0.954) to the optimized weights (0.968) is supportable from very few labels, and the held-out gap is essentially zero.

## What this means for the paper

Two things slot in cleanly once your `feat/gradient-descent-draft` lands.

First, the optimized AUC can be reported in the paper as `0.968 (held-out)` rather than `0.968 (in-sample)` — the additional word carries real methodological weight under reviewer scrutiny and costs nothing.

Second, the same calibration / evaluation split can be reused for the threshold-selection work that is still parked in the paper's future-work list (Experiment #2). One split, two methodological loose ends closed.

## Output and reproducibility

The held-out wrapper writes a JSON payload to `results/<timestamp>/optimization_holdout/holdout_results.json` containing the configuration, both AUCs, the gap, the converged weights, and optimizer metadata. The run reported above lives at `results/20260515_092726/optimization_holdout/holdout_results.json`.

```
uv run python scripts/optimize_weights_holdout.py \
    --run-dir results/20260515_002159/combined
```

By default the wrapper uses the five features in `optimized_weights.json` and `holdout_frac = 0.5`. Both are CLI flags (`--features`, `--holdout-frac`, `--seed`) for sweeps over alternative feature subsets or seeds.

## Status

The validation closes one open methodological concern with the optimizer. Two follow-ups are still natural next steps, neither of which is blocking.

The first is multi-seed evaluation: re-run the held-out wrapper at seeds 0–9 and report mean ± std on the eval AUC. With the current gap at 0.0008 we expect this to confirm the result, but it is the standard rigor for the paper's statistical-significance experiment.

The second is replacing Nelder-Mead with a smooth surrogate (e.g., sigmoid-relaxed pairwise AUC) so the optimizer can use proper gradient-based methods (L-BFGS-B) and accept L1/L2 regularization. The current 0.97 result is already strong enough that this is more of a robustness improvement than a result-changing change.
