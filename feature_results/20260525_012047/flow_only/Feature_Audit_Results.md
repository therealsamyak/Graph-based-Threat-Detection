# Feature Audit Results

## Summary

- Calibration edges: 65,780 (17 redteam)
- Evaluation edges: 65,782 (18 redteam)
- AUC threshold: 0.0
- Selected features: 19

## Selected Features

- `src_burst_score`
- `dst_inter_arrival_mean`
- `dst_inter_arrival_std`
- `dst_out_degree`
- `dst_total_degree`
- `edge_rarity`
- `dst_active_duration`
- `is_unusual_dst_port`
- `dst_in_degree`
- `src_active_duration`
- `src_out_degree`
- `dst_betweenness_centrality`
- `dst_burst_score`
- `src_total_degree`
- `is_ntlm`
- `src_inter_arrival_mean`
- `src_in_degree`
- `src_betweenness_centrality`
- `src_inter_arrival_std`

## Ranked Features

| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| src_burst_score | 0.806806 | 237 | 0.024717 | 0.674419 | 0.557758 | 0.11666 | yes | 0.807493 |
| dst_inter_arrival_mean | 0.798647 | 6350 | 6.04218e+09 | 107492 | 46932.3 | 60559.5 | yes | 0.837162 |
| dst_inter_arrival_std | 0.777305 | 6034 | 8.53031e+09 | 153665 | 75854.3 | 77810.5 | yes | 0.825482 |
| dst_out_degree | 0.746584 | 113 | 7.07746 | 2.17697 | 4.50428 | -2.3273 | yes | 0.721425 |
| dst_total_degree | 0.700436 | 146 | 6.89529 | 3.20867 | 5.31676 | -2.10809 | yes | 0.666724 |
| edge_rarity | 0.694988 | 2853 | 0.070651 | 0.116802 | 0.144454 | -0.0276524 | yes | 0.751155 |
| dst_active_duration | 0.676633 | 6259 | 6.52381e+11 | 680094 | 1.18657e+06 | -506478 | yes | 0.606366 |
| is_unusual_dst_port | 0.675709 | 2 | 0.105038 | 0.470588 | 0.11917 | 0.351418 | yes | 0.663581 |
| dst_in_degree | 0.656583 | 105 | 6.53396 | 2.81672 | 4.744 | -1.92728 | yes | 0.598971 |
| src_active_duration | 0.565683 | 7724 | 6.93815e+11 | 1.7072e+06 | 1.19914e+06 | 508058 | yes | 0.561553 |
| src_out_degree | 0.553472 | 127 | 6.97326 | 6.16121 | 4.87172 | 1.28948 | yes | 0.549982 |
| dst_betweenness_centrality | 0.550244 | 4488 | 0.0015327 | 5.06095e-05 | 0.0166266 | -0.016576 | yes | 0.527404 |
| dst_burst_score | 0.544163 | 220 | 0.0241735 | 0.594221 | 0.564466 | 0.0297553 | yes | 0.561219 |
| src_total_degree | 0.5426 | 161 | 6.95471 | 6.20658 | 5.47647 | 0.73011 | yes | 0.538562 |
| is_ntlm | 0.5 | 1 | 0 | 0 | 0 | 0 | yes | 0.5 |
| is_network_logon | 0.5 | 1 | 0 | 0 | 0 | 0 | no |  |
| is_success_auth | 0.5 | 1 | 0 | 0 | 0 | 0 | no |  |
| src_inter_arrival_mean | 0.491234 | 7841 | 7.21148e+09 | 3616.94 | 40282.8 | -36665.8 | yes | 0.486269 |
| src_in_degree | 0.469109 | 106 | 7.8672 | 3.13549 | 4.3074 | -1.1719 | yes | 0.471268 |
| src_betweenness_centrality | 0.444642 | 4429 | 0.000939006 | 0.000149255 | 0.012054 | -0.0119047 | yes | 0.447601 |
| src_inter_arrival_std | 0.414869 | 6956 | 7.06562e+09 | 30434 | 62294.8 | -31860.9 | yes | 0.410346 |

## Duplicate Features

- `is_network_logon` duplicates `is_ntlm`
- `is_success_auth` duplicates `is_ntlm`

## Recommendations

### Top 5 Features

- `src_burst_score` (AUC 0.8068)
- `dst_inter_arrival_mean` (AUC 0.7986)
- `dst_inter_arrival_std` (AUC 0.7773)
- `dst_out_degree` (AUC 0.7466)
- `dst_total_degree` (AUC 0.7004)

### Features to Drop

- `is_network_logon`
- `is_success_auth`
