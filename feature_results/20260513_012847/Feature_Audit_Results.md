# Feature Audit Results

## Summary

- Calibration edges: 182,402 (153 redteam)
- Evaluation edges: 182,400 (152 redteam)
- AUC threshold: 0.6
- Selected features: 21

## Selected Features

- `is_ntlm`
- `source_fan_out`
- `dst_in_degree`
- `is_network_logon`
- `dst_fan_out_ratio`
- `dst_total_degree`
- `edge_rarity`
- `weight_norm`
- `dst_inter_arrival_std`
- `src_out_degree`
- `dst_inter_arrival_mean`
- `src_total_degree`
- `src_inter_arrival_mean`
- `src_in_degree`
- `src_inter_arrival_std`
- `src_active_duration`
- `byte_per_packet`
- `protocol_rarity`
- `dst_betweenness_centrality`
- `dst_out_degree`
- `src_burst_score`

## Ranked Features

| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| is_ntlm | 0.932809 | 2 | 0.0919362 | 0.96732 | 0.101702 | 0.865619 | yes | 0.93263 |
| source_fan_out | 0.90604 | 769 | 0.0505023 | 0.974506 | 0.695578 | 0.278928 | yes | 0.9037 |
| dst_in_degree | 0.818715 | 195 | 8.88726 | 3.11989 | 6.88502 | -3.76513 | yes | 0.818357 |
| is_network_logon | 0.817056 | 2 | 0.224488 | 0.973856 | 0.339744 | 0.634112 | yes | 0.816936 |
| dst_fan_out_ratio | 0.816931 | 748 | 0.0644074 | 0.596167 | 0.287163 | 0.309004 | yes | 0.808968 |
| dst_total_degree | 0.812463 | 243 | 6.97366 | 4.09024 | 7.29645 | -3.20621 | yes | 0.812577 |
| edge_rarity | 0.808487 | 3631 | 0.0609464 | 0.521981 | 0.123271 | 0.39871 | yes | 0.833581 |
| weight_norm | 0.808487 | 3631 | 6.48048e-08 | 1.15846e-05 | 4.05117e-05 | -2.89271e-05 | yes | 0.833581 |
| dst_inter_arrival_std | 0.784675 | 11192 | 6.78263e+09 | 129817 | 58932.5 | 70884.3 | yes | 0.773958 |
| src_out_degree | 0.78282 | 166 | 4.38823 | 6.70251 | 4.31459 | 2.38793 | yes | 0.78092 |
| dst_inter_arrival_mean | 0.778171 | 11235 | 2.83434e+09 | 53734.1 | 26765 | 26969.1 | yes | 0.775133 |
| src_total_degree | 0.759762 | 233 | 5.26784 | 6.72833 | 4.74979 | 1.97854 | yes | 0.759619 |
| src_inter_arrival_mean | 0.754318 | 13938 | 2.86836e+09 | 4466.91 | 45625.3 | -41158.4 | yes | 0.748115 |
| src_in_degree | 0.746184 | 174 | 6.09749 | 3.05768 | 2.99279 | 0.0648956 | yes | 0.747761 |
| src_inter_arrival_std | 0.730054 | 13822 | 9.32391e+09 | 29468.3 | 113839 | -84370.4 | yes | 0.722332 |
| src_active_duration | 0.705475 | 13648 | 5.22307e+11 | 2.12742e+06 | 1.44121e+06 | 686213 | yes | 0.710195 |
| byte_per_packet | 0.636716 | 12140 | 0.0583849 | 0.00227842 | 0.141676 | -0.139398 | yes | 0.638799 |
| protocol_rarity | 0.634408 | 5 | 0.00265517 | 0.998254 | 0.971462 | 0.0267916 | yes | 0.639712 |
| dst_betweenness_centrality | 0.627366 | 10354 | 4.25739e-07 | 4.16022e-05 | 0.000421128 | -0.000379526 | yes | 0.635001 |
| dst_out_degree | 0.625115 | 157 | 8.77536 | 3.50193 | 4.64254 | -1.1406 | yes | 0.637174 |
| src_burst_score | 0.621801 | 454 | 0.0254362 | 0.529734 | 0.591747 | -0.0620121 | yes | 0.615656 |
| is_success_auth | 0.585618 | 2 | 0.213269 | 0.862745 | 0.69151 | 0.171235 | no |  |
| dst_burst_score | 0.579669 | 437 | 0.0561486 | 0.567169 | 0.46729 | 0.0998788 | no |  |
| dst_active_duration | 0.531458 | 11039 | 7.96403e+11 | 1.37938e+06 | 1.43834e+06 | -58960.6 | no |  |
| is_unusual_dst_port | 0.5 | 1 | 0 | 0 | 0 | 0 | no |  |
| temporal_decay_weight | 0.5 | 1 | 0 | 1 | 1 | 0 | no |  |
| duration_zscore | 0.438644 | 75 | 0.281839 | -0.00420753 | -0.00024382 | -0.00396371 | no |  |
| src_betweenness_centrality | 0.16631 | 10983 | 1.52236e-07 | 1.39903e-05 | 0.000114533 | -0.000100543 | no |  |

## Duplicate Features

- None detected

## Recommendations

### Top 5 Features

- `is_ntlm` (AUC 0.9328)
- `source_fan_out` (AUC 0.9060)
- `dst_in_degree` (AUC 0.8187)
- `is_network_logon` (AUC 0.8171)
- `dst_fan_out_ratio` (AUC 0.8169)

### Features to Drop

- `is_success_auth`
- `dst_burst_score`
- `dst_active_duration`
- `is_unusual_dst_port`
- `temporal_decay_weight`
- `duration_zscore`
- `src_betweenness_centrality`
