# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0014 | 0.0000 | 0.0000 | 50.64s | 19749/s |
| auth_only | LANL-2015 | 0.0000 | 0.0006 | 0.0000 | 0.9094 | 110.05s | 9087/s |
| combined | LANL-2015 | 0.0000 | 0.0005 | 0.0000 | 0.9456 | 294.93s | 6781/s |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0543 | 0.1065 | 0.6353 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.4487 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: isolation_forest (DAPT2020 — 1.0000)
- **Best f1**: oneclass_svm (DAPT2020 — 0.1065)
- **Best auc**: combined (LANL-2015 — 0.9456)
- **Lowest FPR**: combined (LANL-2015 — 0.0005)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
