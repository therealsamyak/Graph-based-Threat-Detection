# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| auth_only | LANL-2015 | 0.8344 | 0.0190 | 0.0617 | 0.9657 | 3803.65s | 27362/s |
| combined | LANL-2015 | 0.9416 | 0.0208 | 0.0515 | 0.9656 | 6440.68s | 21067/s |
| flow_only | LANL-2015 | 0.0130 | 0.1000 | 0.0006 | 0.5154 | 721.67s | 43803/s |

## Best Method Per Metric

- **Best recall**: combined (LANL-2015 — 0.9416)
- **Best f1**: auth_only (LANL-2015 — 0.0617)
- **Best auc**: auth_only (LANL-2015 — 0.9657)
- **Lowest FPR**: auth_only (LANL-2015 — 0.0190)
