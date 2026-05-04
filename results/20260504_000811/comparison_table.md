# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Edge recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0000 | 0.0043 | 0.0000 | 0.0000 | 8.04s | 6222/s |
| auth_only | LANL-2015 | 0.0000 | 0.0000 | 0.0032 | 0.0000 | 0.0000 | 11.48s | 4355/s |
| combined | LANL-2015 | 0.0000 | 0.0000 | 0.0019 | 0.0000 | 0.0000 | 25.95s | 3854/s |
| isolation_forest | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00s | 0/s |
| lof | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00s | 0/s |
| ocsvm | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00s | 0/s |
| elliptic_envelope | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00s | 0/s |
| pca_reconstruction | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.00s | 0/s |
| oneclass_svm | DAPT2020 | 0.1533 | 0.0000 | 0.0551 | 0.0145 | 0.5512 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 1.0000 | 0.0000 | 1.0000 | 0.0055 | 0.6255 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: isolation_forest (DAPT2020 — 1.0000)
- **Best f1**: oneclass_svm (DAPT2020 — 0.0145)
- **Best auc**: isolation_forest (DAPT2020 — 0.6255)
- **Lowest FPR**: isolation_forest (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
### Combined vs auth_only
