# Report Integration Guide

This guide explains how to merge the three draft `.tex` files into `Final_Report.tex`.

## Files in `report/`

| File                                    | Purpose                                                         |
| --------------------------------------- | --------------------------------------------------------------- |
| `Final_Report.tex`                      | Current report — DO NOT edit directly until ready to merge      |
| `feature_selection_metrics_draft.tex`   | **Draft 1** — New subsection on held-out AUC feature audit      |
| `weight_optimization_draft.tex`         | **Draft 2** — New subsection on Nelder-Mead weight optimization |
| `existing_sections_revisions_draft.tex` | **Draft 3** — Rewrites of existing sections that need updating  |

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

**Why:** Need to mention `feature.py` and `main.py` as the two CLI entry points, and reference Nelder-Mead optimization.

### Step 6: Update Cross-References

After all edits, search for broken references:

- `\ref{sec:edge_scoring}` — should still work (label preserved)
- Add `\ref{sec:feature_selection}` and `\ref{sec:weight_optimization}` where appropriate
- The new Edge Scoring section already references both labels

## Summary of Section Numbering After Merge

| #   | Section                   | Status                                                   |
| --- | ------------------------- | -------------------------------------------------------- |
| 4.1 | Graph Construction        | Unchanged                                                |
| 4.2 | Feature Extraction        | Modified (removed Future Work, added reference to audit) |
| 4.3 | Feature Selection Metrics | **NEW** (Draft 1)                                        |
| 4.4 | Weight Optimization       | **NEW** (Draft 2)                                        |
| 4.5 | Edge Scoring              | **REWRITTEN** (Draft 3, Revision 1)                      |
| 4.6 | Path Scoring              | Unchanged                                                |
| 4.7 | Threshold Selection       | **REWRITTEN** (Draft 3, Revision 3)                      |
| 5.4 | Implementation            | **REWRITTEN** (Draft 3, Revision 2)                      |

## What NOT to Change

- **Baseline methods** (Isolation Forest, One-Class SVM, auth-only, flow-only) — keep as-is for now
- **Results section** (Section 6) — update numbers when final pipeline run completes, but the structure stays
- **Discussion and Conclusion** — update after final results
