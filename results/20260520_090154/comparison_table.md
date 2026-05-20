# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| auth_only | LANL-2015 | 0.8344 | 0.0190 | 0.0617 | 0.9657 | 3575.52s | 29107/s |
| combined | LANL-2015 | 0.9416 | 0.0208 | 0.0515 | 0.9656 | 5967.81s | 22736/s |
| flow_only | LANL-2015 | 0.0130 | 0.1000 | 0.0006 | 0.5154 | 586.88s | 53864/s |

## Best Method Per Metric

- **Best recall**: combined (LANL-2015 — 0.9416)
- **Best f1**: auth_only (LANL-2015 — 0.0617)
- **Best auc**: auth_only (LANL-2015 — 0.9657)
- **Lowest FPR**: auth_only (LANL-2015 — 0.0190)
