# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0130 | 0.0297 | 0.0019 | 0.5785 | 510.61s | 61909/s |
| auth_only | LANL-2015 | 0.7468 | 0.0296 | 0.0364 | 0.9508 | 5170.61s | 20128/s |
| combined | LANL-2015 | 0.6623 | 0.0196 | 0.0387 | 0.9544 | 7026.45s | 19311/s |
| graph_combined | DAPT2020 | 0.2222 | 0.0194 | 0.1000 | 0.6012 | 1.24s | 70121/s |
| oneclass_svm | DAPT2020 | 0.2232 | 0.1004 | 0.0955 | 0.6463 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 0.0069 | 0.0500 | 0.0051 | 0.4487 | 0.00s | 0/s |
| oneclass_svm | LANL-2015 | 0.4918 | 0.0982 | 0.0083 | 0.7059 | 0.00s | 0/s |
| isolation_forest | LANL-2015 | 0.7410 | 0.0500 | 0.0241 | 0.9397 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: auth_only (LANL-2015 — 0.7468)
- **Best f1**: graph_combined (DAPT2020 — 0.1000)
- **Best auc**: combined (LANL-2015 — 0.9544)
- **Lowest FPR**: graph_combined (DAPT2020 — 0.0194)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
- recall: +4994.6%
- f1: +1936.8%
### Combined vs auth_only
- recall: -11.3%
- f1: +6.3%
