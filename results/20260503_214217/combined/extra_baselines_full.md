# Extra-baselines comparison

- run dir: `/Users/ipehlivan/Documents/GitHub/Graph-based-Threat-Detection/results/20260502_165755/combined`
- edges evaluated (after mask): **364,802** (305 red-team)
- features: edge_rarity, src_out_degree, dst_in_degree, is_ntlm, is_network_logon, is_success_auth, source_fan_out, weight_norm, is_unusual_dst_port, protocol_rarity, byte_per_packet, duration_zscore

## Results (sorted by AUC desc)

| method | auc | f1 | recall | precision | fpr |
|---|---|---|---|---|---|
| isolation_forest | 0.9397 | 0.0241 | 0.741 | 0.0122 | 0.05 |
| elliptic_envelope | 0.7741 | 0.0 | 0.0 | 0.0 | 0.05 |
| oneclass_svm | 0.7059 | 0.0083 | 0.4918 | 0.0042 | 0.0982 |
| pca_reconstruction | 0.6672 | 0.0011 | 0.0328 | 0.0005 | 0.05 |
| lof | 0.4925 | 0.0076 | 0.2066 | 0.0039 | 0.0447 |


_Shared baselines: 2387.8s · Extra baselines: 71.4s_
