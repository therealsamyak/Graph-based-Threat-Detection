# Baseline Comparison: Graph-based vs SVM vs Isolation Forest

## Per-Variant Results

### combined

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.9448 | 0.0295 | 0.0371 | 0.0189 | 0.9756 |
| SVC (supervised) | 0.2662 | 0.0006 | 0.3333 | 0.4457 | 0.9554 |
| One-Class SVM | 0.0162 | 0.0010 | 0.0204 | 0.0273 | 0.7678 |
| Isolation Forest | 0.0292 | 0.0050 | 0.0147 | 0.0098 | 0.9388 |

### auth_only

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.9448 | 0.0293 | 0.0463 | 0.0237 | 0.9781 |
| SVC (supervised) | 0.2143 | 0.0295 | 0.0312 | 0.0168 | 0.9534 |
| One-Class SVM | 0.0130 | 0.0500 | 0.0012 | 0.0006 | 0.5442 |
| Isolation Forest | 0.2695 | 0.0995 | 0.0124 | 0.0063 | 0.9030 |

### flow_only

| Method | Recall | FPR | F1 | Precision | AUC |
|--------|--------|-----|----|-----------|-----|
| Graph-based | 0.0130 | 0.1000 | 0.0006 | 0.0003 | 0.5154 |
| SVC (supervised) | 0.0032 | 0.0300 | 0.0009 | 0.0005 | 0.6520 |
| One-Class SVM | 0.0227 | 0.0049 | 0.0219 | 0.0212 | 0.7500 |
| Isolation Forest | 0.0162 | 0.0049 | 0.0157 | 0.0152 | 0.8246 |
