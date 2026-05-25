# Baseline Comparison: Graph-based vs One-Class SVM vs Isolation Forest

## Per-Variant Results

### auth_only

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.9221 | 0.0100 | 0.1778 | 0.0984 | 0.9842 |
| One-Class SVM | 0.9416 | 0.1068 | 0.0399 | 0.0204 | 0.9234 |
| Isolation Forest | 0.9448 | 0.0291 | 0.1322 | 0.0710 | 0.9726 |

### combined

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.2110 | 0.0050 | 0.0591 | 0.0344 | 0.9590 |
| One-Class SVM | 0.0519 | 0.0009 | 0.0652 | 0.0874 | 0.8000 |
| Isolation Forest | 0.5877 | 0.0291 | 0.0626 | 0.0330 | 0.9572 |

### flow_only

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.0682 | 0.0298 | 0.0099 | 0.0053 | 0.9626 |
| One-Class SVM | 0.0292 | 0.1018 | 0.0026 | 0.0013 | 0.6622 |
| Isolation Forest | 0.0422 | 0.0999 | 0.0038 | 0.0020 | 0.7182 |
