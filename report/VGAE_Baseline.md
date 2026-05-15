# VGAE Baseline — First-Run Result (Honest Negative)

## TL;DR

A Variational Graph Autoencoder, trained as a one-class anomaly detector on the LANL-2015 combined graph with default-ish hyperparameters, reaches **eval AUC ≈ 0.50** — chance level. Two training paradigms were tried (benign-only positives in the calibration half, and all calibration-half edges as positives); both produced the same result. The reconstruction loss converges cleanly, but the per-edge reconstruction probability does not separate red-team edges from benign ones on this dataset.

This is the **negative-outcome branch** explicitly anticipated in `report/VGAE_Rationale.md`. The paper claim it supports is *"we evaluated VGAE as an unsupervised graph-aware baseline; default configurations did not produce useful anomaly signal on this dataset, and we leave further investigation of GNN-based unsupervised methods to future work."*

## Result

| Method | Configuration | Eval AUC | Wall time |
|---|---|---|---|
| **VGAE (benign-only positives)** | 2-layer GCN encoder, hidden=64, latent=32, lr=0.01, 100 epochs, MPS | **0.4954** | 39 s |
| **VGAE (all calibration positives)** | same, label-blind training | **0.4968** | 39 s |
| Isolation Forest (reference, tabular unsupervised) | 100 trees, contamination 0.05 | 0.9098 | — |
| Supervised LR on 5 features (reference, supervised) | L2, balanced classes | 0.9733 | — |

The result is reproducible: same data (`results/20260512_post_fix/combined`), same stratified split (seed 42, 50/50 calibration/evaluation), same eval protocol. The cal-AUC and eval-AUC agree to within 0.0001, so the model is not over-fitting; it is converging cleanly to a representation that simply does not discriminate red-team activity.

## What went into this run

Held to the spec in `report/VGAE_Rationale.md`. No hyperparameter tuning, no multi-seed, no architecture exploration. Configuration choices were standard PyG-tutorial defaults:

- **Data**: post-bug-fix LANL combined graph (91,589 nodes, 512,529 edges, 305 red-team in masked set).
- **Node features**: the 9 numeric columns in `node_features.csv` (degrees, fan-out ratio, inter-arrival statistics, burst score, active duration, betweenness), StandardScaler-fit on benign nodes only.
- **Encoder**: two GCN layers (input → 64 → 32). Mean aggregation, ReLU activation, latent dim 32.
- **Decoder**: inner-product (`P(edge u,v) = σ(z_u · z_v)`), standard PyG `VGAE` wrapper.
- **Training**: Adam, lr=0.01, 100 epochs, reconstruction loss + KL term scaled by 1/N. Negative-sampling 1× the positive count per epoch.
- **Per-edge anomaly score**: `softplus(-z_u · z_v)` — high when reconstruction probability is low.
- **Device**: MPS on Apple M3 Pro. 100 epochs in 39 seconds.

## What I checked before concluding "negative"

Two non-trivial diagnostic decisions:

**Training-positive mode**: I tried both `benign-only-cal` (the canonical one-class setup, matching IF / OCSVM) and `all-cal` (label-blind, training on every calibration edge including red-team). The hypothesis behind testing both was that VGAE's message-passing layers see *all* edges in the graph (including red-team) regardless of which subset is used as reconstruction targets, so the benign-only filter at the loss level may have no practical effect. The empirical result confirmed this: both modes produced eval AUC within 0.002 of 0.50.

**Reconstruction-loss convergence**: the loss decreased monotonically from epoch 1 (loss = 1724) to epoch 100 (loss = 1.54). The model is fitting the reconstruction objective successfully; it is just learning a latent representation in which red-team edges are indistinguishable from benign edges by inner-product similarity.

## Why this likely fails

Three hypotheses worth flagging for follow-up work, each consistent with the observed pattern:

**1. Inner-product reconstruction is the wrong scoring function for this graph's structure.** VGAE was developed for citation networks where anomalous edges (a paper citing an unrelated paper) really are between dissimilar nodes. On the LANL graph, red-team edges connect *authenticated network entities* — they are structurally plausible, just rare. The inner-product `z_u · z_v` cannot distinguish "structurally plausible and frequent" from "structurally plausible and rare." A different decoder (e.g., negative-energy of a Gaussian mixture, or a learned distance metric) might.

**2. The graph is dense and homophilic.** With average degree ≈ 11 (512K edges / 91K nodes, undirected) and most edges concentrated in a small core of frequently-communicating hosts, the latent embeddings z become similar for almost all node pairs. The inner products `z_u · z_v` are bunched in a narrow range; their rank order carries little signal about anomaly.

**3. Per-edge red-team labels are noisy from a structural perspective.** The 305 red-team edges originate overwhelmingly from a single attacker host (`C17693`, 93.6% of red-team activity). VGAE has no way to learn that "edges from C17693" are anomalous because C17693 looks like a moderately busy host in the message-passing graph. Methods that use C17693's identity (the personalized-PageRank-from-known-attacker result from `Optimizer_Holdout_Validation.md`) capture this; structural VGAE cannot.

## What this means for the paper

The result fits the rationale doc's predicted negative branch. Reportable as:

> *"We evaluated a Variational Graph Autoencoder as an unsupervised graph-aware baseline. With standard configuration (2-layer GCN encoder, latent dimension 32, 100 epochs of reconstruction + KL training on benign edges), eval AUC on the held-out half was 0.495 — at chance. The model converged on its training objective but learned a latent representation in which inner-product similarity does not separate red-team edges from benign ones. We attribute this to a mismatch between the inner-product decoder and the structural plausibility of lateral-movement edges on this dataset; richer GNN-based unsupervised approaches (graph autoencoders with non-inner-product decoders, contrastive learning, or one-class graph SVM) are left to future work."*

The headline ladder of unsupervised baselines on this dataset, with VGAE included:

| Method | Type | Eval AUC |
|---|---|---|
| Isolation Forest (tabular) | one-class | 0.9098 |
| Elliptic Envelope (tabular) | one-class | 0.7741 |
| PCA Reconstruction (tabular) | one-class | 0.6672 |
| One-Class SVM (tabular) | one-class | 0.6670 |
| Local Outlier Factor (tabular) | one-class | 0.4925 |
| **VGAE (graph-aware)** | **one-class** | **0.4954** |

VGAE underperforms every tabular one-class baseline except LOF, despite using graph topology. This is genuinely informative: it tells us that graph topology under standard VGAE reconstruction objectives does not by itself produce a useful anomaly signal on this dataset.

The companion supervised graph-aware result (LR on graph-derived features at AUC 0.973, plus the +0.036 graph-vs-tabular ablation in `report/Optimizer_Holdout_Validation.md`) shows that the graph-derived *features* carry plenty of signal. The negative VGAE result is therefore not "graph data doesn't help" — it is "this particular unsupervised GNN training objective doesn't extract the signal."

## Follow-ups (out of scope for tonight)

Three concrete next experiments if anyone wants to push further on the unsupervised graph-aware angle:

**Different decoder**. Replace the inner-product decoder with a learned MLP that takes the concatenation `[z_u || z_v]` and predicts edge existence. This is the "decoder MLP" variant in some GNN-anomaly literature; it can learn non-symmetric and non-similarity-based reconstruction signals.

**Contrastive / self-supervised training**. Methods like DGI (Deep Graph Infomax) or GraphCL pre-train embeddings without any explicit edge-existence objective, and downstream anomaly scoring works on the embeddings themselves rather than on reconstruction. These often outperform VGAE for anomaly detection on graphs.

**Hyperparameter search**. We used a single configuration. Sweeping latent dimension (16, 32, 64, 128), encoder depth (2 vs 3 layers), and learning rate (0.001, 0.005, 0.01) might find a configuration where the AUC moves off chance. Risk: with chance-level performance at the default config, sweeping may not help — VGAE may genuinely be wrong for this problem rather than mis-tuned.

If a future contributor wants to retry, the data adapter (`scripts/vgae/build_data.py`) and training loop (`scripts/vgae/train_vgae.py`) are reusable as scaffolding; only the model and loss need to change.

## Output

- `results/20260515_103505/vgae/vgae_results.json` (benign-only-cal run, AUC 0.4954)
- `results/20260515_103505/vgae/training_log.csv` (per-epoch loss and cal-AUC)
- `results/20260515_103708/vgae/vgae_results.json` (all-cal run, AUC 0.4968)

## Reproducibility

```bash
# Dedicated venv (one-time)
uv venv .venv-vgae --python /Library/Frameworks/Python.framework/Versions/3.13/bin/python3
uv pip install --python .venv-vgae/bin/python --python-platform aarch64-apple-darwin \
    -r scripts/vgae/requirements.txt

# Verify (Phase 0)
.venv-vgae/bin/python scripts/vgae/setup_check.py

# Build PyG Data (Phase 1)
.venv-vgae/bin/python scripts/vgae/build_data.py \
    --run-dir results/20260512_post_fix/combined \
    --output  .venv-vgae/cache/vgae_data.pt

# Train + eval (Phase 2-3)
.venv-vgae/bin/python scripts/vgae/train_vgae.py \
    --data .venv-vgae/cache/vgae_data.pt \
    --training-positives benign-only-cal
```

## Status

This baseline is complete as a first-run experiment. The negative result is honest and documented. No PR opened tonight — branch sits on origin for team review tomorrow. If anyone disagrees with the framing or wants to invest more time in the follow-ups above, please comment on the rationale doc and we can revisit.
