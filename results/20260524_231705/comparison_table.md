# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| auth_only | LANL-2015 | 0.9221 | 0.0064 | 0.1778 | 0.9842 | 4102.71s | 25367/s |
| combined | LANL-2015 | 0.2110 | 0.0036 | 0.0591 | 0.9590 | 6524.41s | 20796/s |
| flow_only | LANL-2015 | 0.0682 | 0.0298 | 0.0099 | 0.9626 | 497.36s | 63558/s |

## Best Method Per Metric

- **Best recall**: auth_only (LANL-2015 — 0.9221)
- **Best f1**: auth_only (LANL-2015 — 0.1778)
- **Best auc**: auth_only (LANL-2015 — 0.9842)
- **Lowest FPR**: combined (LANL-2015 — 0.0036)
