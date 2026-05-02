# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 10.75s | 5/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 21.45s | 2/s |
| combined | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 31.60s | 3/s |

## Best Method Per Metric

- **Best recall**: flow_only (LANL-2015 — 0.0000)
- **Best f1**: flow_only (LANL-2015 — 0.0000)
- **Best auc**: flow_only (LANL-2015 — 0.0000)
- **Lowest FPR**: flow_only (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
