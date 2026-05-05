# Lateral Movement Detection — Method Comparison

| Method | Dataset | Recall | Fpr | F1 | Auc | Latency | Throughput |
|--------|---------|------|------|------|------|------|------|
| flow_only | LANL-2015 | 0.0130 | 0.0297 | 0.0019 | 0.5785 | 475.96s | 66416/s |
| auth_only | LANL-2015 | 0.7468 | 0.0296 | 0.0364 | 0.9508 | 5162.15s | 20161/s |
| combined | LANL-2015 | 0.6623 | 0.0196 | 0.0387 | 0.9544 | 7042.27s | 19267/s |
| graph_combined | DAPT2020 | 0.2222 | 0.0194 | 0.1000 | 0.6012 | 1.29s | 67129/s |
| oneclass_svm | DAPT2020 | 1.0000 | 1.0000 | 0.0119 | 0.5500 | 0.00s | 0/s |
| isolation_forest | DAPT2020 | 0.1111 | 0.0107 | 0.0769 | 0.5500 | 0.00s | 0/s |
| oneclass_svm | LANL-2015 | 0.4295 | 0.1250 | 0.0057 | 0.6670 | 0.00s | 0/s |
| isolation_forest | LANL-2015 | 0.5639 | 0.0466 | 0.0197 | 0.9098 | 0.00s | 0/s |

## Best Method Per Metric

- **Best recall**: oneclass_svm (DAPT2020 — 1.0000)
- **Best f1**: graph_combined (DAPT2020 — 0.1000)
- **Best auc**: combined (LANL-2015 — 0.9544)
- **Lowest FPR**: isolation_forest (DAPT2020 — 0.0107)

## Relative Improvement: Combined vs Single-Source

### Combined vs flow_only
- recall: +4994.6%
- f1: +1936.8%
### Combined vs auth_only
- recall: -11.3%
- f1: +6.3%
