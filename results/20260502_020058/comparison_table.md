# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 10.85s | 5/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 20.85s | 2/s |
| combined | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 32.29s | 3/s |
| oneclass_svm | DAPT2020 | 0.0000 | 0.1400 | 0.0000 | nan | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 0.0000 | 0.2200 | 0.0000 | nan | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: flow_only (LANL-2015 — 0.0000)
- **Best f1**: flow_only (LANL-2015 — 0.0000)
- **Best auc**: flow_only (LANL-2015 — 0.0000)
- **Lowest FPR**: flow_only (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
