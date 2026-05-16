# Feature Audit Results

## Summary

- Calibration edges: 182,400 (152 redteam)
- Evaluation edges: 182,402 (153 redteam)
- AUC threshold: 0.0
- Selected features: 27

## Selected Features

- `is_ntlm`
- `src_fan_out_ratio`
- `dst_in_degree`
- `dst_fan_out_ratio`
- `is_network_logon`
- `dst_total_degree`
- `edge_rarity`
- `dst_inter_arrival_std`
- `src_out_degree`
- `dst_inter_arrival_mean`
- `src_total_degree`
- `src_inter_arrival_mean`
- `src_in_degree`
- `src_inter_arrival_std`
- `src_active_duration`
- `protocol_rarity`
- `byte_per_packet`
- `dst_betweenness_centrality`
- `dst_out_degree`
- `src_burst_score`
- `is_success_auth`
- `dst_burst_score`
- `dst_active_duration`
- `is_unusual_dst_port`
- `temporal_decay_weight`
- `duration_zscore`
- `src_betweenness_centrality`

## Ranked Features

| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| is_ntlm | 0.932702 | 2 | 0.0919327 | 0.967105 | 0.101702 | 0.865403 | yes | 0.932738 |
| src_fan_out_ratio | 0.906017 | 769 | 0.0505024 | 0.97449 | 0.695579 | 0.278911 | yes | 0.903737 |
| dst_in_degree | 0.818902 | 195 | 8.88723 | 3.12071 | 6.88501 | -3.7643 | yes | 0.818167 |
| dst_fan_out_ratio | 0.817846 | 748 | 0.0644078 | 0.596888 | 0.287164 | 0.309725 | yes | 0.80811 |
| is_network_logon | 0.816969 | 2 | 0.224488 | 0.973684 | 0.339746 | 0.633938 | yes | 0.817023 |
| dst_total_degree | 0.812193 | 243 | 6.97363 | 4.09321 | 7.29644 | -3.20322 | yes | 0.812842 |
| edge_rarity | 0.808463 | 3631 | 0.060947 | 0.524319 | 0.123272 | 0.401047 | yes | 0.833453 |
| weight_norm | 0.808463 | 3631 | 0.060947 | 0.524319 | 0.123272 | 0.401047 | no |  |
| dst_inter_arrival_std | 0.785191 | 11192 | 6.78269e+09 | 130123 | 58932.8 | 71189.8 | yes | 0.773521 |
| src_out_degree | 0.78275 | 166 | 4.38823 | 6.7016 | 4.3146 | 2.387 | yes | 0.780998 |
| dst_inter_arrival_mean | 0.778364 | 11235 | 2.83437e+09 | 53817.8 | 26765.2 | 27052.6 | yes | 0.774963 |
| src_total_degree | 0.759639 | 233 | 5.26786 | 6.72743 | 4.7498 | 1.97763 | yes | 0.759741 |
| src_inter_arrival_mean | 0.754215 | 13938 | 2.86838e+09 | 4481.11 | 45625.2 | -41144.1 | yes | 0.748257 |
| src_in_degree | 0.74603 | 174 | 6.09755 | 3.05717 | 2.99279 | 0.0643809 | yes | 0.747899 |
| src_inter_arrival_std | 0.729952 | 13822 | 9.32396e+09 | 29507.4 | 113839 | -84331.1 | yes | 0.722485 |
| src_active_duration | 0.705403 | 13648 | 5.22309e+11 | 2.12723e+06 | 1.44121e+06 | 686018 | yes | 0.710235 |
| protocol_rarity | 0.635628 | 5 | 0.0654366 | 0.00445882 | 0.141739 | -0.13728 | yes | 0.638089 |
| byte_per_packet | 0.634516 | 12234 | 0.00301561 | 0.00166193 | 0.0285065 | -0.0268446 | yes | 0.639319 |
| dst_betweenness_centrality | 0.628123 | 10354 | 4.25742e-07 | 4.18623e-05 | 0.000421127 | -0.000379265 | yes | 0.634209 |
| dst_out_degree | 0.624329 | 157 | 8.7754 | 3.5056 | 4.64252 | -1.13692 | yes | 0.63788 |
| src_burst_score | 0.621702 | 454 | 0.0254364 | 0.529786 | 0.591746 | -0.0619607 | yes | 0.615797 |
| is_success_auth | 0.585167 | 2 | 0.21327 | 0.861842 | 0.691508 | 0.170334 | yes | 0.599109 |
| dst_burst_score | 0.577766 | 437 | 0.0561489 | 0.566514 | 0.467289 | 0.099225 | yes | 0.54868 |
| dst_active_duration | 0.53008 | 11039 | 7.96408e+11 | 1.38387e+06 | 1.43834e+06 | -54470.6 | yes | 0.565569 |
| is_unusual_dst_port | 0.502491 | 2 | 0.0178071 | 0.0131579 | 0.0181401 | -0.00498222 | yes | 0.509369 |
| temporal_decay_weight | 0.5 | 1 | 0 | 1 | 1 | 0 | yes | 0.5 |
| duration_zscore | 0.438676 | 75 | 0.281842 | -0.00423521 | -0.000243822 | -0.00399139 | yes | 0.43718 |
| source_fan_out | 0.21725 | 166 | 4.48257e+06 | 899.118 | 915.078 | -15.9599 | no |  |
| src_betweenness_centrality | 0.166413 | 10983 | 1.52237e-07 | 1.39865e-05 | 0.000114534 | -0.000100548 | yes | 0.161812 |

## Duplicate Features

- `source_fan_out` duplicates `src_out_degree`
- `weight_norm` duplicates `edge_rarity`

## Recommendations

### Top 5 Features

- `is_ntlm` (AUC 0.9327)
- `src_fan_out_ratio` (AUC 0.9060)
- `dst_in_degree` (AUC 0.8189)
- `dst_fan_out_ratio` (AUC 0.8178)
- `is_network_logon` (AUC 0.8170)

### Features to Drop

- `source_fan_out`
- `weight_norm`
