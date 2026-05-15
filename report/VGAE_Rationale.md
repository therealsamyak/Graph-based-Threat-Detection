# VGAE Baseline: Why We're Adding This (Rationale)

## TL;DR

The current paper compares the graph-based pipeline against five **unsupervised tabular** baselines (Isolation Forest, One-Class SVM, Local Outlier Factor, Elliptic Envelope, PCA reconstruction). All of them top out around AUC 0.94. There is no **unsupervised graph-aware** baseline in the comparison. A Variational Graph Autoencoder (VGAE) fills exactly that gap. This branch adds it as a single, self-contained baseline so the paper can claim or disclaim "graph-aware unsupervised methods close the gap to supervised" with empirical evidence rather than speculation.

The work is fully isolated: a dedicated `.venv-vgae` (gitignored), all code under `scripts/vgae/`, no teammate-owned files modified, no PR opened until the team reviews.

## Where VGAE fits in the existing comparison

After the held-out validation work in `report/Optimizer_Holdout_Validation.md`, the baseline ladder looks like this:

| Method | Supervision | Uses graph structure? | Eval AUC (held-out) |
|---|---|---|---|
| Isolation Forest, OCSVM, LOF, EE, PCA | One-class (unsupervised) | No (tabular features only) | 0.49–0.94 |
| Logistic regression on per-edge features | Supervised | Partial (some features are graph-derived) | 0.96–0.99 |
| Combined-graph pipeline (manual weights + paths) | Supervised | Yes | 0.954 |
| `WeightOptimizer` (Nelder-Mead) | Supervised | Yes | 0.968 |
| LR + personalized PageRank from `C17693` | Supervised + known-attacker seed | Yes (multi-hop) | 0.996 |
| **VGAE (this branch)** | **Unsupervised** | **Yes** | **TBD** |

VGAE is the only cell that is both unsupervised *and* graph-aware. Every existing unsupervised baseline ignores graph topology; every existing graph-aware method uses labels. Adding VGAE lets us answer a question the paper currently cannot:

> "How much of the supervision gap (one-class IF at AUC 0.94 versus supervised LR at AUC 0.99) is explained by *graph structure* versus *having labels at training time*?"

If a graph-aware unsupervised method closes most of that gap, then the paper's strongest claim shifts from "supervised methods help" to "**graph-aware methods help, even without labels**" — a structurally stronger contribution.

## What VGAE actually does

VGAE is a graph neural network trained as a *link prediction* model. The encoder is a two-layer Graph Convolutional Network that produces a low-dimensional latent vector for each node by aggregating that node's neighborhood. The decoder reconstructs the probability that an edge between two nodes exists, as the sigmoid of the inner product of their latent vectors: `P(edge u, v) = σ(z_u · z_v)`.

Adapted for anomaly detection, the protocol is:

1. Train on **benign edges only**, treating them as positives and random non-existing edges as negatives. The model learns what "normal" edges look like.
2. At evaluation time, score every edge in the held-out evaluation half by `-log σ(z_u · z_v)`. Edges the model assigns *low* reconstruction probability are unexpected under the learned benign distribution — i.e., anomalous.
3. Compute AUC against the red-team labels in the held-out half.

This is a one-class adaptation of VGAE — directly comparable to how IF and OCSVM are configured in our pipeline (train on benign only, score all). The same stratified 50/50 calibration / evaluation split used by every other ablation in `Optimizer_Holdout_Validation.md` is used here.

## What outcomes mean

There are three honest outcomes for tonight's first run, each with a different paper implication.

**Eval AUC roughly 0.94–0.96** — the most likely outcome. VGAE matches or modestly improves on the strongest tabular unsupervised baseline. Reportable as "graph-aware unsupervised learning marginally improves on tabular unsupervised methods on this dataset"; honest but not headline-worthy.

**Eval AUC roughly 0.96–0.98** — the strong outcome. VGAE closes most of the supervision gap (IF 0.94 versus LR 0.99) without using labels at training time. Reportable as "graph-aware unsupervised learning closes the supervision gap, suggesting graph structure carries most of the discriminative signal"; this would be a headline-grade contribution and shifts the paper's story significantly.

**Eval AUC roughly 0.85 or below** — the negative outcome. VGAE fails to compete with even tabular unsupervised baselines on this problem. Reportable as "first attempt at graph-aware unsupervised lateral-movement detection on LANL-2015 produced AUC X; we hypothesize Y and Z and leave further investigation to future work." A short negative result in the paper, not a setback.

All three outcomes are publishable. None invalidate the existing work; they just shift which framing is the strongest paper claim.

## What this costs and what we are explicitly not doing

This is a one-night first-run. Out of scope tonight:

- Hyperparameter search (latent dimension, learning rate, encoder depth, dropout)
- Multi-seed evaluation (only seed 42 tonight; multi-seed is a paper-readiness follow-up)
- Other GNN architectures (no GAT, R-GCN, TGN — VGAE only)
- Modified training paradigms (no semi-supervised variants, no negative-sampling tuning)
- Pull request — the branch sits on origin for team review tomorrow

Total wall time tonight: approximately three hours of focused work, plus this rationale doc. All dependencies isolated to a `.venv-vgae` virtual environment that touches nothing the main project uses.

## The decision the team has

If anyone on the team disagrees with this direction — believes VGAE is the wrong baseline to add, or has a different priority for tonight, or has concerns about adding a tenth method to the comparison table — please comment on this document on GitHub before VGAE results are committed and we can either change scope or stop entirely. The implementation work is straightforward to abandon if the direction is wrong; the rationale above is the part where input is most valuable.

Otherwise, results follow in `report/VGAE_Baseline.md` on the same branch (`ip/vgae-baseline`) in a few hours.

## Files in this branch

- `.gitignore` (single line added for `.venv-vgae/`)
- `scripts/vgae/requirements.txt` — pinned torch + PyG versions, install instructions
- `scripts/vgae/setup_check.py` — Phase 0 gate (already verified MPS-available on this machine)
- `scripts/vgae/build_data.py` — graph CSV to PyG `Data` adapter (pending Phase 1)
- `scripts/vgae/train_vgae.py` — VGAE encoder + training + held-out eval (pending Phase 2-3)
- `report/VGAE_Rationale.md` — this document
- `report/VGAE_Baseline.md` — results writeup (pending Phase 4)
- `results/<timestamp>/vgae/vgae_results.json` — output JSON (pending Phase 3)
