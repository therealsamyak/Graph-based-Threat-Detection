# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| auth_only | LANL-2015 | 0.9416 | 0.0632 | 0.0219 | 0.8977 | 3742.52s | 27808/s |
| combined | LANL-2015 | 0.0000 | 0.0712 | 0.0000 | 0.7835 | 6338.84s | 21405/s |
| flow_only | LANL-2015 | 0.0195 | 0.0010 | 0.0273 | 0.9210 | 501.04s | 63091/s |

## Best Method Per Metric

- **Best recall**: auth_only (LANL-2015 — 0.9416)
- **Best f1**: flow_only (LANL-2015 — 0.0273)
- **Best auc**: flow_only (LANL-2015 — 0.9210)
- **Lowest FPR**: flow_only (LANL-2015 — 0.0010)
