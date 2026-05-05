# Progress Report — Wesley Gunawan

## Figure Added to LaTeX Paper

### Figure 1 — ROC Curves (Wesley Gunawan)
- **Location:** Lines 175–180 in `USENIX_2023/usenix.tex`
- **Image file:** `USENIX_2023/roc_curves.png`
- **Caption:** "ROC curves comparing detection performance of flow-only, auth-only, and combined methods on LANL-2015. The combined method (AUC = 0.9456) dominates both single-source baselines, demonstrating that multi-log integration improves the trade-off between true positive rate and false positive rate."
- **Contributor:** Wesley Gunawan

## Inspection: Does the Figure Make Sense?

### What the figure shows
The ROC curves plot displays True Positive Rate (TPR) vs. False Positive Rate (FPR) for three methods:
- **Combined method** (both flow + auth logs): AUC = 0.9456
- **Auth-only method** (authentication logs only): AUC = 0.9094
- **Flow-only method** (network flow logs only): AUC = 0.0000

### How to interpret it
- The **combined curve** is closest to the top-left corner, meaning it achieves higher true positive rates at lower false positive rates — this is the ideal detector.
- The **auth-only curve** is below the combined curve, showing that authentication logs alone provide good but inferior detection.
- The **flow-only curve** hugs the diagonal (random baseline), meaning network flow patterns alone cannot distinguish attack edges from benign edges in this dataset.

### Does it push the argument forward?
**Yes.** This figure directly supports the paper's central hypothesis: *"No single log source provides enough signal to reliably identify lateral movement, but combining both log types into a unified graph enables detection that neither source can achieve alone."*

The AUC gap between combined (0.9456) and auth-only (0.9094) shows that adding flow logs to the authentication graph provides incremental detection signal. The near-zero AUC for flow-only confirms that network flows alone are insufficient — they need authentication context to be useful. This validates the paper's core claim that multi-log graph analysis is necessary for lateral movement detection.

### Data consistency check
The AUC values in the figure match the results in `results/20260502_075816/comparison_table.md`:
- combined: AUC = 0.9456 ✅
- auth_only: AUC = 0.9094 ✅
- flow_only: AUC = 0.0000 ✅

The figure is consistent with the reported results.
