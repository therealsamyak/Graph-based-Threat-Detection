# Feature Audit Results

## Summary

- Calibration edges: 182,402 (153 redteam)
- Evaluation edges: 182,400 (152 redteam)
- AUC threshold: 0.0
- Selected features: 28

## Selected Features

- `is_ntlm`
- `src_fan_out_ratio`
- `dst_in_degree`
- `is_network_logon`
- `dst_fan_out_ratio`
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
- `edge_index`
- `duration_zscore`
- `src_betweenness_centrality`

## Ranked Features

| feature | AUC | n_unique | variance | mean_redteam | mean_benign | delta_mean | selected | eval_auc |
|---|---:|---:|---:|---:|---:|---:|---|---:|
| is_ntlm | 0.932809 | 2 | 0.0919362 | 0.96732 | 0.101702 | 0.865619 | yes | 0.93263 |
| src_fan_out_ratio | 0.90604 | 769 | 0.0505023 | 0.974506 | 0.695578 | 0.278928 | yes | 0.9037 |
| dst_in_degree | 0.818715 | 195 | 8.88726 | 3.11989 | 6.88502 | -3.76513 | yes | 0.818357 |
| is_network_logon | 0.817056 | 2 | 0.224488 | 0.973856 | 0.339744 | 0.634112 | yes | 0.816936 |
| dst_fan_out_ratio | 0.816931 | 748 | 0.0644074 | 0.596167 | 0.287163 | 0.309004 | yes | 0.808968 |
| dst_total_degree | 0.812463 | 243 | 6.97366 | 4.09024 | 7.29645 | -3.20621 | yes | 0.812577 |
| edge_rarity | 0.808487 | 3631 | 0.0609464 | 0.521981 | 0.123271 | 0.39871 | yes | 0.833581 |
| weight_norm | 0.808487 | 3631 | 0.0609464 | 0.521981 | 0.123271 | 0.39871 | no |  |
| dst_inter_arrival_std | 0.784675 | 11192 | 6.78263e+09 | 129817 | 58932.5 | 70884.3 | yes | 0.773958 |
| src_out_degree | 0.78282 | 166 | 4.38823 | 6.70251 | 4.31459 | 2.38793 | yes | 0.78092 |
| dst_inter_arrival_mean | 0.778171 | 11235 | 2.83434e+09 | 53734.1 | 26765 | 26969.1 | yes | 0.775133 |
| src_total_degree | 0.759762 | 233 | 5.26784 | 6.72833 | 4.74979 | 1.97854 | yes | 0.759619 |
| src_inter_arrival_mean | 0.754318 | 13938 | 2.86836e+09 | 4466.91 | 45625.3 | -41158.4 | yes | 0.748115 |
| src_in_degree | 0.746184 | 174 | 6.09749 | 3.05768 | 2.99279 | 0.0648956 | yes | 0.747761 |
| src_inter_arrival_std | 0.730054 | 13822 | 9.32391e+09 | 29468.3 | 113839 | -84370.4 | yes | 0.722332 |
| src_active_duration | 0.705475 | 13648 | 5.22307e+11 | 2.12742e+06 | 1.44121e+06 | 686213 | yes | 0.710195 |
| protocol_rarity | 0.635666 | 5 | 0.0654361 | 0.00442968 | 0.141738 | -0.137309 | yes | 0.638063 |
| byte_per_packet | 0.634562 | 12234 | 0.00301559 | 0.00165106 | 0.0285063 | -0.0268553 | yes | 0.639301 |
| dst_betweenness_centrality | 0.627366 | 10354 | 4.25739e-07 | 4.16022e-05 | 0.000421128 | -0.000379526 | yes | 0.635001 |
| dst_out_degree | 0.625115 | 157 | 8.77536 | 3.50193 | 4.64254 | -1.1406 | yes | 0.637174 |
| src_burst_score | 0.621801 | 454 | 0.0254362 | 0.529734 | 0.591747 | -0.0620121 | yes | 0.615656 |
| is_success_auth | 0.585618 | 2 | 0.213269 | 0.862745 | 0.69151 | 0.171235 | yes | 0.598745 |
| dst_burst_score | 0.579669 | 437 | 0.0561486 | 0.567169 | 0.46729 | 0.0998788 | yes | 0.546581 |
| dst_active_duration | 0.531458 | 11039 | 7.96403e+11 | 1.37938e+06 | 1.43834e+06 | -58960.6 | yes | 0.564402 |
| is_unusual_dst_port | 0.502534 | 2 | 0.0178069 | 0.0130719 | 0.01814 | -0.00506812 | yes | 0.509369 |
| temporal_decay_weight | 0.5 | 1 | 0 | 1 | 1 | 0 | yes | 0.5 |
| edge_index | 0.495558 | 182402 | 2.37135e+10 | 273620 | 273244 | 376.057 | yes | 0.512708 |
| duration_zscore | 0.438644 | 75 | 0.281839 | -0.00420753 | -0.00024382 | -0.00396371 | yes | 0.562799 |
| source_fan_out | 0.21718 | 166 | 4.48253e+06 | 899.353 | 915.073 | -15.7205 | no |  |
| src_betweenness_centrality | 0.16631 | 10983 | 1.52236e-07 | 1.39903e-05 | 0.000114533 | -0.000100543 | yes | 0.838116 |

## Duplicate Features

- `weight_norm` duplicates `edge_rarity`
- `source_fan_out` duplicates `src_out_degree`

## Recommendations

### Top 5 Features

- `is_ntlm` (AUC 0.9328)
- `src_fan_out_ratio` (AUC 0.9060)
- `dst_in_degree` (AUC 0.8187)
- `is_network_logon` (AUC 0.8171)
- `dst_fan_out_ratio` (AUC 0.8169)

### Features to Drop

- `weight_norm`
- `source_fan_out`
