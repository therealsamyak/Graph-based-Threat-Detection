# Feature Audit Results

## Summary

- Calibration edges: 130,686 (151 redteam)
- Evaluation edges: 130,687 (151 redteam)
- AUC threshold: 0.0
- Selected features: 20

## Selected Features

- `src_in_degree`
- `is_ntlm`
- `src_out_degree`
- `edge_rarity`
- `src_total_degree`
- `src_betweenness_centrality`
- `src_inter_arrival_mean`
- `dst_in_degree`
- `src_inter_arrival_std`
- `src_active_duration`
- `is_network_logon`
- `dst_inter_arrival_mean`
- `dst_betweenness_centrality`
- `dst_inter_arrival_std`
- `dst_out_degree`
- `dst_active_duration`
- `dst_burst_score`
- `is_success_auth`
- `src_burst_score`
- `is_unusual_dst_port`

## Ranked Features

| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| src_in_degree | 0.939573 | 125 | 0.827786 | 0.0688557 | 1.41624 | -1.34739 | yes | 0.951457 |
| is_ntlm | 0.909389 | 2 | 0.122146 | 0.960265 | 0.141487 | 0.818778 | yes | 0.925341 |
| src_out_degree | 0.892641 | 95 | 2.92977 | 6.08373 | 3.57838 | 2.50535 | yes | 0.901144 |
| edge_rarity | 0.889092 | 2482 | 0.0583114 | 0.604329 | 0.118293 | 0.486037 | yes | 0.909237 |
| src_total_degree | 0.880317 | 170 | 2.91735 | 6.08901 | 3.75688 | 2.33213 | yes | 0.893632 |
| dst_total_degree | 0.845283 | 180 | 5.14691 | 4.1599 | 8.04122 | -3.88133 | no |  |
| src_betweenness_centrality | 0.845051 | 7759 | 2.94276e-09 | 1.18218e-11 | 4.29994e-06 | -4.29992e-06 | yes | 0.858529 |
| src_inter_arrival_mean | 0.843501 | 13376 | 3.78781e+09 | 7921.85 | 60821.1 | -52899.3 | yes | 0.861703 |
| dst_in_degree | 0.833376 | 149 | 7.19815 | 3.20254 | 7.8422 | -4.63966 | yes | 0.878883 |
| src_inter_arrival_std | 0.814931 | 13258 | 1.04231e+10 | 45061.3 | 142395 | -97333.7 | yes | 0.834791 |
| src_active_duration | 0.764564 | 13109 | 5.01103e+11 | 2.11818e+06 | 1.30119e+06 | 816984 | yes | 0.779025 |
| is_network_logon | 0.750106 | 2 | 0.249318 | 0.97351 | 0.473298 | 0.500212 | yes | 0.758954 |
| dst_inter_arrival_mean | 0.625498 | 8350 | 3.94736e+09 | 73985.9 | 54979.3 | 19006.6 | yes | 0.624173 |
| dst_betweenness_centrality | 0.617169 | 6838 | 4.39919e-08 | 4.12147e-05 | 0.000147671 | -0.000106457 | yes | 0.655178 |
| dst_inter_arrival_std | 0.599659 | 8348 | 9.81802e+09 | 145176 | 115942 | 29234.1 | yes | 0.613901 |
| dst_out_degree | 0.579684 | 81 | 2.89395 | 3.15058 | 2.63547 | 0.515115 | yes | 0.586379 |
| dst_active_duration | 0.55769 | 8230 | 8.40087e+11 | 1.33704e+06 | 1.20764e+06 | 129393 | yes | 0.544098 |
| dst_burst_score | 0.544449 | 271 | 0.0980866 | 0.560828 | 0.478722 | 0.0821058 | yes | 0.548931 |
| is_success_auth | 0.538718 | 2 | 0.0339955 | 0.887417 | 0.964852 | -0.0774351 | yes | 0.542048 |
| src_burst_score | 0.529528 | 300 | 0.0281969 | 0.598885 | 0.594439 | 0.00444606 | yes | 0.48894 |
| is_unusual_dst_port | 0.5 | 1 | 0 | 0 | 0 | 0 | yes | 0.5 |

## Duplicate Features

- `dst_total_degree` duplicates `dst_in_degree`

## Recommendations

### Top 5 Features

- `src_in_degree` (AUC 0.9396)
- `is_ntlm` (AUC 0.9094)
- `src_out_degree` (AUC 0.8926)
- `edge_rarity` (AUC 0.8891)
- `src_total_degree` (AUC 0.8803)

### Features to Drop

- `dst_total_degree`
