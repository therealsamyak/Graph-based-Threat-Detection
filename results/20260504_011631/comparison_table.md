# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Edge recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0000 | 0.0857 | 0.0004 | 0.0000 | 0.5779 | 325.00s | 97265/s |
| auth_only | LANL-2015 | 0.0032 | 0.9040 | 0.0001 | 0.0056 | 0.9542 | 2926.30s | 35565/s |
| combined | LANL-2015 | 0.0000 | 0.9705 | 0.0001 | 0.0000 | 0.9380 | 4516.06s | 30045/s |
| isolation_forest | LANL-2015 | 0.3961 | 0.0000 | 0.0498 | 0.0094 | 0.9059 | 0.00s | 0/s |
| lof | LANL-2015 | 0.1818 | 0.0000 | 0.0299 | 0.0071 | 0.6467 | 0.00s | 0/s |
| ocsvm | LANL-2015 | 0.3896 | 0.0000 | 0.0990 | 0.0047 | 0.6381 | 0.00s | 0/s |
| elliptic_envelope | LANL-2015 | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.8232 | 0.00s | 0/s |
| pca_reconstruction | LANL-2015 | 0.0032 | 0.0000 | 0.1001 | 0.0000 | 0.7548 | 0.00s | 0/s |
| oneclass_svm | DAPT2020 | 0.1612 | 0.0000 | 0.0543 | 0.1065 | 0.6353 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 1.0000 | 0.0000 | 1.0000 | 0.0550 | 0.4487 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: isolation_forest (DAPT2020 — 1.0000)
- **Best edge recall**: combined (LANL-2015 — 0.9705)
- **Best f1**: oneclass_svm (DAPT2020 — 0.1065)
- **Best auc**: auth_only (LANL-2015 — 0.9542)
- **Lowest FPR**: elliptic_envelope (LANL-2015 — 0.0000)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
- auc: +62.3%
### Combined vs auth_only
- auc: -1.7%
