# Lateral Movement Detection — Method Comparison

| Method | Variant | Recall | Fpr | F1 | Auc | Precision |
|--------|---------|------|------|------|------|------|
| Graph-Based | Auth Only | 0.9221 | 0.0064 | 0.1778 | 0.9842 | — |
| Isolation Forest | Auth Only | 0.9448 | 0.0291 | 0.1322 | 0.9726 | 0.0710 |
| One-Class SVM | Auth Only | 0.9416 | 0.1068 | 0.0399 | 0.9234 | 0.0204 |
| Graph-Based | Combined | 0.2110 | 0.0036 | 0.0591 | 0.9590 | — |
| Isolation Forest | Combined | 0.5877 | 0.0291 | 0.0626 | 0.9572 | 0.0330 |
| One-Class SVM | Combined | 0.0519 | 0.0009 | 0.0652 | 0.8000 | 0.0874 |
| Graph-Based | Flow Only | 0.0682 | 0.0298 | 0.0099 | 0.9626 | — |
| Isolation Forest | Flow Only | 0.0422 | 0.0999 | 0.0038 | 0.7182 | 0.0020 |
| One-Class SVM | Flow Only | 0.0292 | 0.1018 | 0.0026 | 0.6622 | 0.0013 |

## Best Method Per Metric

- **Best recall**: Isolation Forest (Auth Only) — 0.9448
- **Best f1**: Graph-Based (Auth Only) — 0.1778
- **Best auc**: Graph-Based (Auth Only) — 0.9842
- **Lowest FPR**: One-Class SVM (Combined) — 0.0009
