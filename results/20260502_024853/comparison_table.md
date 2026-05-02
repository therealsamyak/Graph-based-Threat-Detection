# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0004 | 0.0000 | 0.0000 | 502.78s | 62873/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 3751.05s | 27745/s |
| combined | LANL-2015 | 0.0000 | 0.0001 | 0.0000 | 0.0000 | 5812.34s | 23344/s |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0543 | 0.1065 | 0.6353 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.4487 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: isolation_forest (DAPT2020 — 1.0000)
- **Best f1**: oneclass_svm (DAPT2020 — 0.1065)
- **Best auc**: oneclass_svm (DAPT2020 — 0.6353)
- **Lowest FPR**: auth_only (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
