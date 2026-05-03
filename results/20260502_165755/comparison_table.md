# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0130 | 0.0297 | 0.0019 | 0.5785 | 585.55s | 53985/s |
| auth_only | LANL-2015 | 0.7468 | 0.0296 | 0.0364 | 0.9508 | 6142.25s | 16944/s |
| combined | LANL-2015 | 0.6623 | 0.0196 | 0.0387 | 0.9544 | 7598.11s | 17858/s |
| oneclass_svm | DAPT2020 | 1.0000 | 1.0000 | 0.0550 | 0.6463 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 0.0069 | 0.0500 | 0.0051 | 0.4487 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: oneclass_svm (DAPT2020 — 1.0000)
- **Best f1**: oneclass_svm (DAPT2020 — 0.0550)
- **Best auc**: combined (LANL-2015 — 0.9544)
- **Lowest FPR**: combined (LANL-2015 — 0.0196)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
- recall: +4994.6%
- f1: +1936.8%
### Combined vs auth_only
- recall: -11.3%
- f1: +6.3%
