# Extra-baselines comparison

- run dir: `/Users/ipehlivan/Documents/GitHub/Graph-based-Threat-Detection/results/20260502_165755/combined`
- edges evaluated (after mask): **100,305** (305 red-team)
- features: edge_rarity, src_out_degree, dst_in_degree, is_ntlm, is_network_logon, is_success_auth, source_fan_out, weight_norm, is_unusual_dst_port, protocol_rarity, byte_per_packet, duration_zscore

## Results (sorted by AUC desc)

| method | auc | f1 | recall | precision | fpr |
|---|---|---|---|---|---|
| isolation_forest | 0.9449 | 0.0841 | 0.7639 | 0.0445 | 0.05 |
| lof | 0.8877 | 0.0761 | 0.6098 | 0.0406 | 0.044 |
| elliptic_envelope | 0.7727 | 0.0 | 0.0 | 0.0 | 0.05 |
| oneclass_svm | 0.7002 | 0.0271 | 0.4689 | 0.014 | 0.101 |
| pca_reconstruction | 0.6683 | 0.0034 | 0.0295 | 0.0018 | 0.05 |


_Shared baselines: 195.6s · Extra baselines: 21.1s_
