# Minor Edits for Final_Report.tex
# These are small text changes, deletions, and swaps throughout the report.
# Line numbers reference Final_Report.tex as of the current version.

## 1. Feature Extraction — Remove Future Work, add audit reference
**Target:** Section 4.2, lines 91-96
**Action:** DELETE the Future Work block:
```
\begin{itemize}
\item \textit{Future work:}
\begin{itemize}
\item Narrow feature set to 3-5 per flow type. Likely will just pick based on common sense / what appears interesting.
\end{itemize}
\end{itemize}
```
**Replace with:**
```latex
The feature set was narrowed from the full 23 features to the selected discriminative features using the held-out AUC audit described in Section~\ref{sec:feature_selection}.
```

## 2. Edge Scoring — Remove Future Work
**Target:** Old Section 4.3, lines 124-129
**Action:** DELETE the Future Work block:
```
\begin{itemize}
\item \textit{Future work:}
\begin{itemize}
\item The specific features and weights are still being refined.
\end{itemize}
\end{itemize}
```
No replacement needed — the new Edge Scoring rewrite already references the optimizer.

## 3. Implementation — Remove completed Future Work items
**Target:** Section 5.5, lines 193-202
**Action:** DELETE these two lines from the Future Work list:
- `Run ablation testing on reduced feature set across graph scoring and baselines`
- `Optimize scoring weights via grid search / Bayesian optimization / other method`

Keep remaining items:
- Run statistical significance testing on all results
- Measure computational cost (CPU, memory, wall-clock time) across all methods
- The current results are not finalized

## 4. Baseline Methods — Remove Future Work
**Target:** Section 5.3, lines 173-179
**Action:** DELETE the entire Future Work block:
```
\begin{itemize}
\item \textit{Future work:}
\begin{itemize}
\item Finalize baseline implementations / parameters and how data is injested by them
\item If necessary, tune hyperparameters for baseline methods (currently scikit-learn defaults)
\end{itemize}
\end{itemize}
```
No replacement needed — baselines are now implemented and results are in the draft results.

## 5. Results — Soften "Numbers are not final" warnings
**Target:** Section 6, multiple locations

**Line ~214** (paragraph after Figure 1):
CHANGE: `\textbf{Numbers are not final and results are subject to change.}`
TO: `The pipeline results use optimized weights; held-out validation (Section~\ref{sec:holdout_weight}) confirms these AUC figures are not in-sample artifacts.`

**Line ~225** (paragraph after Figure 2):
CHANGE: `\textbf{Numbers are not final and subject to change.}`
TO: `The scoring function and threshold remain the same across the initial run and the held-out evaluation.`

**Line ~244** (Table 1 caption):
CHANGE: `\textbf{Numbers are not final.}`
TO: `AUC figures validated under held-out protocol in Section~\ref{sec:holdout_weight}.`

**Line ~249** (paragraph after Table 1):
CHANGE: `\textbf{Numbers are not final and subject to change.}`
TO: `These results are corroborated by the held-out evaluation in Section~\ref{sec:holdout_weight}.`

## 6. Methodology intro — Add weight optimization mention
**Target:** Section 3, lines 67-68
**Action:** CHANGE the current text:
```
We test whether a graph built from both network flow and authentication logs
detects more lateral movement pairs than graphs from either source alone.
We also compare against two standard unsupervised anomaly detectors applied
to the same edge feature vector.
```
TO:
```
We test whether a graph built from both network flow and authentication logs
detects more lateral movement pairs than graphs from either source alone.
Edge scoring weights are optimized automatically via Nelder-Mead to maximize
ROC AUC. We also compare against two standard unsupervised anomaly detectors
applied to the same edge feature vector.
```
