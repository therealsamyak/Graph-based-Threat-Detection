# Report Integration Guide

This guide explains how to merge the four draft `.tex` files into `Final_Report.tex`.

## Files in `report/`

| File | Purpose |
|------|---------|
| `Final_Report.tex` | Current report — DO NOT edit directly until ready to merge |
| `feature_selection_metrics_draft.tex` | **Draft 1** — New subsection on held-out AUC feature audit |
| `weight_optimization_draft.tex` | **Draft 2** — New subsection on Nelder-Mead weight optimization |
| `existing_sections_revisions_draft.tex` | **Draft 3** — Rewrites of existing sections that need updating |
| `weight_optimization_eval_draft.tex` | **Draft 4** — Evaluation results: held-out validation, LR baseline, tabular/graph ablation, graph extensions, synthesis |

## Merge Order

Follow these steps **in order**. Each step references line numbers in `Final_Report.tex`.

### Step 1: Insert Draft 1 — Feature Selection Metrics

**Where:** After the end of Section 4.2 (Feature Extraction), before Section 4.3 (Edge Scoring).

**What to do:**

1. Find the `\end{itemize}` that closes the "Future work" block at the end of Section 4.2 (around line 96)
2. Delete the entire "Future work" block (lines 91–96):
   ```latex
   \begin{itemize}
   \item \textit{Future work:}
   \begin{itemize}
   \item Narrow feature set to 3-5 per flow type...
   \end{itemize}
   \end{itemize}
   ```
3. Replace it with:
   ```latex
   The feature set was narrowed from the full 23 features to five discriminative features using the held-out AUC audit described in Section~\ref{sec:feature_selection}.
   ```
4. Immediately after that sentence, paste the entire contents of `feature_selection_metrics_draft.tex`
5. Add a label `\label{sec:feature_selection}` at the start of the pasted subsection (it should already be there)

**New section numbering:** This becomes Section 4.3 (Feature Selection Metrics).

### Step 2: Insert Draft 2 — Weight Optimization

**Where:** Right after the newly inserted Section 4.3 (Feature Selection Metrics), before what was Section 4.3 (Edge Scoring).

**What to do:**

1. Paste the entire contents of `weight_optimization_draft.tex`
2. The label `\label{sec:weight_optimization}` is already in the draft

**New section numbering:** This becomes Section 4.4 (Weight Optimization). All subsequent sections shift by 2.

### Step 3: Replace Edge Scoring Section

**Where:** Old Section 4.3 (now Section 4.5 after the two insertions).

**What to do:**

1. Delete the **entire** old Edge Scoring subsection (the `\subsection{Edge Scoring}` block with the two equations for $s_\text{auth}$ and $s_\text{flow}$, and the auth multiplier paragraph, plus its "Future work" block)
2. Replace it with the "REVISION 1: Edge Scoring" block from `existing_sections_revisions_draft.tex`
3. Update the label to `\label{sec:edge_scoring}`

**Why:** The old section described separate auth/flow formulas with hand-picked weights and a $1.5\times$ auth multiplier. The new section describes a single unified weighted sum using optimized weights.

### Step 4: Update Threshold Selection Section

**Where:** Old Section 4.5 (now Section 4.7 after insertions).

**What to do:**

1. Delete the **entire** old Threshold Selection subsection including its "Future work" block
2. Replace with the "REVISION 3: Threshold Selection" block from `existing_sections_revisions_draft.tex`

**Why:** The "move to held-out validation set" future work item is now moot — weight optimization already uses proper AUC evaluation.

### Step 5: Update Implementation Subsection

**Where:** Section 5.4 (Implementation).

**What to do:**

1. Delete the **entire** old Implementation subsection
2. Replace with the "REVISION 2: Implementation" block from `existing_sections_revisions_draft.tex`
3. In the "Future work" item list, delete the line `Optimize scoring weights via grid search / Bayesian optimization / other method` (this is done)

3. Also delete the `Run ablation testing on reduced feature set` line (now done — Draft 4)

**Why:** Need to mention `feature.py`, `main.py`, and `analysis/` scripts, and reference Nelder-Mead optimization. Weight optimization and ablation testing are complete.

### Step 6: Remove Baseline Methods "Future work"

**Where:** Section 5.3 (Baseline Methods), lines 173–179.

**What to do:**
1. Delete the entire "Future work" block (lines 173–179) — baselines are now finalized and reported in Table 1
2. No replacement needed

**Why:** Baselines are implemented and results are in Table~\ref{tab:methods_lanl}.

### Step 7: Soften "Numbers are not final" Warnings

**Where:** Results section (Section 6), multiple locations.

**What to do (from Draft 3, Revision 8):**
1. Line 214: Replace `\textbf{Numbers are not final and results are subject to change.}` with: `The pipeline results use optimized weights; held-out validation (Section~\ref{sec:holdout_weight}) confirms these AUC figures are not in-sample artifacts.`
2. Line 225: Replace `\textbf{Numbers are not final and subject to change.}` with: `The scoring function and threshold remain the same across the initial run and the held-out evaluation.`
3. Line 244 (Table 1 caption): Replace `\textbf{Numbers are not final.}` with: `AUC figures validated under held-out protocol in Section~\ref{sec:holdout_weight}.`
4. Line 249: Replace `\textbf{Numbers are not final and subject to change.}` with: `These results are corroborated by the held-out evaluation in Section~\ref{sec:holdout_weight}.`

**Why:** Held-out validation (Draft 4) confirms the AUC figures are not in-sample artifacts.

### Step 8: Update Methodology Intro

**Where:** Section 3 (Methodology), lines 67–68.

**What to do:**
1. Replace the two-sentence intro with: `We test whether a graph built from both network flow and authentication logs detects more lateral movement pairs than graphs from either source alone. Edge scoring weights are optimized automatically via Nelder-Mead to maximize ROC AUC. We also compare against two standard unsupervised anomaly detectors applied to the same edge feature vector.`

**Why:** The pipeline now includes automated weight optimization.

### Step 9: Insert Draft 4 — Weight Optimization Evaluation Results

**Where:** In the Results section (Section 6), after the existing results content (after Table 1 / `\label{tab:methods_lanl}` and surrounding text), before `\section{Discussion and Limitations}`.

**What to do:**
1. Delete the "Results Draft:" placeholder subsection (lines 251–260) — Draft 4 replaces it with real content
2. Paste the entire contents of `weight_optimization_eval_draft.tex` above `\section{Discussion and Limitations}`
3. The draft's `\ref{tab:methods_lanl}` on line 146 references Table 1 already in Final_Report.tex — this will resolve correctly after merge

**Content added:** 5 new subsections under Results:
- Held-Out Validation of Weight Optimization
- Logistic-Regression Baseline Comparison
- Tabular versus Graph-Derived Feature Ablation
- Graph Feature Extensions
- Decomposing the Detection Improvement

**Cross-references that will work after merge:**

| Label in draft | Defined in | Resolves to |
|----------------|-----------|-------------|
| `\ref{tab:methods_lanl}` | Final_Report.tex | Table 1 (existing results) |
| `\label{sec:holdout_weight}` | weight_optimization_eval_draft.tex | New section |
| `\label{tab:holdout_optimizer}` | weight_optimization_eval_draft.tex | New table |
| `\label{sec:lr_baseline}` | weight_optimization_eval_draft.tex | New section |
| `\label{tab:lr_comparison}` | weight_optimization_eval_draft.tex | New table |
| `\label{sec:tabular_graph_ablation}` | weight_optimization_eval_draft.tex | New section |
| `\label{tab:tabular_graph}` | weight_optimization_eval_draft.tex | New table |
| `\label{sec:graph_extensions}` | weight_optimization_eval_draft.tex | New section |
| `\label{tab:graph_sweep}` | weight_optimization_eval_draft.tex | New table |
| `\label{sec:weight_synthesis}` | weight_optimization_eval_draft.tex | New section |
| `\label{tab:synthesis_axes}` | weight_optimization_eval_draft.tex | New table |
| `\label{tab:auc_budget}` | weight_optimization_eval_draft.tex | New table |

### Step 10: Update Cross-References

After all edits, search for broken references:

- `\ref{sec:edge_scoring}` — should still work (label preserved)
- Add `\ref{sec:feature_selection}` and `\ref{sec:weight_optimization}` where appropriate
- The new Edge Scoring section already references both labels
- Remove or update "Numbers are not final" warnings in the existing Results section if appropriate
- The draft references Equations 1–2 from Edge Scoring — verify numbering matches after insertions

### Optional cleanups after merge

- These are now covered by Revisions 4–7 in Draft 3 (Future work blocks removed/updated)
- Verify equation numbering after insertions (Draft 4 references Equations 1–2 from Edge Scoring)

## Summary of Section Numbering After Merge

| # | Section | Status |
|---|---------|--------|
| 3 | Methodology intro | **UPDATED** (Draft 3, Revision 9) |
| 4.1 | Graph Construction | Unchanged |
| 4.2 | Feature Extraction | Modified (removed Future Work, added reference to audit) |
| 4.3 | Feature Selection Metrics | **NEW** (Draft 1) |
| 4.4 | Weight Optimization | **NEW** (Draft 2) |
| 4.5 | Edge Scoring | **REWRITTEN** (Draft 3, Revision 1) |
| 4.6 | Path Scoring | Unchanged |
| 4.7 | Threshold Selection | **REWRITTEN** (Draft 3, Revision 3) |
| 5.3 | Baseline Methods | Modified (removed Future Work, Draft 3, Revision 7) |
| 5.4 | Implementation | **REWRITTEN** (Draft 3, Revision 2) |
| 6 | Results intro | Modified (softened "not final" warnings, Draft 3, Revision 8) |
| 6.x | Held-Out Validation of Weight Optimization | **NEW** (Draft 4) |
| 6.x | Logistic-Regression Baseline Comparison | **NEW** (Draft 4) |
| 6.x | Tabular versus Graph-Derived Feature Ablation | **NEW** (Draft 4) |
| 6.x | Graph Feature Extensions | **NEW** (Draft 4) |
| 6.x | Decomposing the Detection Improvement | **NEW** (Draft 4) |

## What NOT to Change

- **Baseline methods** (Isolation Forest, One-Class SVM, auth-only, flow-only) — keep all references; 5 pipeline runs remain as-is
- **Discussion and Conclusion** — update after final results
