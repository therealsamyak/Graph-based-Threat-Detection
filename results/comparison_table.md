# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 111.99s | 893/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 13.34s | 7496/s |
| combined | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 338.20s | 296/s |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0543 | 0.1065 | 0.5534 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 0.0069 | 0.0500 | 0.0051 | 0.4785 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: oneclass_svm (DAPT2020 — 0.1612)
- **Best f1**: oneclass_svm (DAPT2020 — 0.1065)
- **Best auc**: oneclass_svm (DAPT2020 — 0.5534)
- **Lowest FPR**: flow_only (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
