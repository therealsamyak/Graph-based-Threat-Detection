# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.1042 | 0.0000 | 0.0000 | 6.79s | 7/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 12.33s | 4/s |
| combined | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 19.07s | 5/s |
| graph_combined | DAPT2020 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.13s | 374/s |

## Best Method Per Metric

- **Best recall**: flow_only (LANL-2015 — 0.0000)
- **Best f1**: flow_only (LANL-2015 — 0.0000)
- **Best auc**: flow_only (LANL-2015 — 0.0000)
- **Lowest FPR**: auth_only (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
