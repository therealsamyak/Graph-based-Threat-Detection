# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0032 | 0.0713 | 0.0002 | 0.0000 | 501.85s | 62990/s |
| auth_only | LANL-2015 | 0.9545 | 0.0632 | 0.0222 | 0.0000 | 5036.03s | 20666/s |
| combined | LANL-2015 | 0.8701 | 0.0707 | 0.0146 | 0.0000 | 6823.57s | 19885/s |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0543 | 0.1065 | 0.6353 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.4487 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: isolation_forest (DAPT2020 — 1.0000)
- **Best f1**: oneclass_svm (DAPT2020 — 0.1065)
- **Best auc**: oneclass_svm (DAPT2020 — 0.6353)
- **Lowest FPR**: oneclass_svm (DAPT2020 — 0.0543)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
- recall: +27090.6%
- f1: +7200.0%
### Combined vs auth_only
- recall: -8.8%
- f1: -34.2%
