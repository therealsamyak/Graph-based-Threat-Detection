# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| auth_only | LANL-2015 | 0.9416 | 0.0632 | 0.0219 | 0.8977 | 3489.11s | 29828/s |
| combined | LANL-2015 | 0.0000 | 0.0712 | 0.0000 | 0.7835 | 6612.22s | 20520/s |
| flow_only | LANL-2015 | 0.0195 | 0.0010 | 0.0273 | 0.9210 | 539.78s | 58563/s |

## Best Method Per Metric

- **Best recall**: auth_only (LANL-2015 — 0.9416)
- **Best f1**: flow_only (LANL-2015 — 0.0273)
- **Best auc**: flow_only (LANL-2015 — 0.9210)
- **Lowest FPR**: flow_only (LANL-2015 — 0.0010)
