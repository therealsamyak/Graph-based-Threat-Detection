"""Train a Variational Graph Autoencoder and evaluate on the held-out split.

The model is trained on benign edges only (one-class learning — directly
comparable to IF / OCSVM / LOF as configured in the rest of the pipeline).
At evaluation time the per-edge anomaly score is the negative log
reconstruction probability, and AUC is computed against red-team labels
on the held-out half of the same stratified 50/50 split used by every
other ablation in report/Optimizer_Holdout_Validation.md (seed 42).

Usage:
    # Phase 1 first (data prep):
    .venv-vgae/bin/python scripts/vgae/build_data.py \\
        --run-dir results/20260512_post_fix/combined \\
        --output  .venv-vgae/cache/vgae_data.pt

    # Then this:
    .venv-vgae/bin/python scripts/vgae/train_vgae.py \\
        --data .venv-vgae/cache/vgae_data.pt \\
        --output-dir results/<timestamp>/vgae

Writes:
    <output-dir>/vgae_results.json   (config + metrics + comparison)
    <output-dir>/training_log.csv    (per-epoch loss + auc-on-cal)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import torch
from sklearn.metrics import roc_auc_score
from torch_geometric.data import Data
from torch_geometric.nn import GCNConv, VGAE
from torch_geometric.utils import negative_sampling

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.feature_audit.scorer import stratified_split  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("train_vgae")


class GraphEncoder(torch.nn.Module):
    def __init__(self, in_dim: int, hidden: int = 64, latent: int = 32):
        super().__init__()
        self.conv1 = GCNConv(in_dim, hidden)
        self.conv_mu = GCNConv(hidden, latent)
        self.conv_logstd = GCNConv(hidden, latent)

    def forward(self, x: torch.Tensor, edge_index: torch.Tensor) -> tuple[torch.Tensor, torch.Tensor]:
        h = torch.relu(self.conv1(x, edge_index))
        return self.conv_mu(h, edge_index), self.conv_logstd(h, edge_index)


def _pick_device() -> torch.device:
    if torch.backends.mps.is_available():
        return torch.device("mps")
    if torch.cuda.is_available():
        return torch.device("cuda")
    return torch.device("cpu")


def _per_edge_score(model: VGAE, z: torch.Tensor, edge_pairs: torch.Tensor) -> np.ndarray:
    """Return anomaly score per edge in edge_pairs (shape 2 x E).

    Higher = more anomalous. We use -log sigmoid(z_u . z_v) = softplus(-z_u . z_v).
    """
    with torch.no_grad():
        src = edge_pairs[0]
        dst = edge_pairs[1]
        dots = (z[src] * z[dst]).sum(dim=-1)
        anomaly = torch.nn.functional.softplus(-dots)
    return anomaly.detach().cpu().numpy()


def _safe_auc(y_true: np.ndarray, scores: np.ndarray) -> float:
    if len(np.unique(y_true)) < 2:
        return float("nan")
    return float(roc_auc_score(y_true, scores))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True, help="Path to vgae_data.pt from build_data.py")
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--hidden", type=int, default=64)
    parser.add_argument("--latent", type=int, default=32)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--epochs", type=int, default=100)
    parser.add_argument("--holdout-frac", type=float, default=0.5)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--device", type=str, default=None, choices=["mps", "cpu", "cuda"],
                        help="Override device autodetect.")
    parser.add_argument("--negative-sample-multiplier", type=int, default=1,
                        help="Number of negative samples per positive (default 1).")
    parser.add_argument("--training-positives", type=str, default="benign-only-cal",
                        choices=["benign-only-cal", "all-cal", "all-edges"],
                        help="Which edges to use as training positives. "
                             "'benign-only-cal' (default): cal-half benign edges only "
                             "(one-class). 'all-cal': all cal-half edges including red-team "
                             "(label-blind). 'all-edges': every edge in graph (label-blind, "
                             "uses eval set too — only for debugging the reconstruction signal).")
    args = parser.parse_args()

    torch.manual_seed(args.seed)
    np.random.seed(args.seed)

    device = torch.device(args.device) if args.device else _pick_device()
    logger.info(f"Device: {device}")

    logger.info(f"Loading data from {args.data}")
    data: Data = torch.load(args.data, weights_only=False)
    n_nodes, in_dim = data.x.shape
    n_edges = data.edge_index.shape[1]
    logger.info(f"Loaded: {n_nodes:,} nodes, {n_edges:,} edges, {in_dim} node-feature dims")
    logger.info(f"Mask keeps {int(data.mask.sum()):,} edges; "
                f"{int(data.y[data.mask].sum())} red-team in masked subset")

    # Held-out split on the masked edges only (same as other ablations).
    masked_indices = torch.nonzero(data.mask, as_tuple=False).squeeze(-1).cpu().numpy()
    masked_labels = data.y[data.mask].cpu().numpy().astype(np.float64)
    cal_local, eval_local = stratified_split(
        np.empty((len(masked_indices), 1)), masked_labels, args.holdout_frac, args.seed
    )
    cal_global = masked_indices[cal_local]
    eval_global = masked_indices[eval_local]
    n_cal_redteam = int(masked_labels[cal_local].sum())
    n_eval_redteam = int(masked_labels[eval_local].sum())
    logger.info(
        f"Stratified split: calibration {len(cal_global):,} edges ({n_cal_redteam} red-team), "
        f"evaluation {len(eval_global):,} edges ({n_eval_redteam} red-team)"
    )

    # Training-positive edges: depends on --training-positives mode
    cal_labels_global = data.y[cal_global].cpu().numpy()
    if args.training_positives == "benign-only-cal":
        train_pos_local = cal_global[cal_labels_global == 0]
    elif args.training_positives == "all-cal":
        train_pos_local = cal_global
    elif args.training_positives == "all-edges":
        train_pos_local = np.arange(n_edges, dtype=np.int64)
    else:
        raise ValueError(f"Unknown training-positives mode: {args.training_positives}")
    train_pos_edges = data.edge_index[:, torch.tensor(train_pos_local, dtype=torch.long)]
    logger.info(f"Training-positive edges ({args.training_positives}): {train_pos_edges.shape[1]:,}")

    # Move everything to device
    x_dev = data.x.to(device)
    full_edge_index_dev = data.edge_index.to(device)
    train_pos_dev = train_pos_edges.to(device)

    encoder = GraphEncoder(in_dim, args.hidden, args.latent)
    model = VGAE(encoder).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=args.lr)
    logger.info(f"Model: 2-layer GCN encoder, hidden={args.hidden}, latent={args.latent}")
    logger.info(f"Optimizer: Adam(lr={args.lr})  Epochs: {args.epochs}")

    # Training loop
    log_rows: list[dict] = []
    t_train_start = time.time()
    for epoch in range(1, args.epochs + 1):
        model.train()
        optimizer.zero_grad()
        z = model.encode(x_dev, full_edge_index_dev)
        # Negative-sample non-edges for the recon_loss objective
        neg_edges = negative_sampling(
            edge_index=train_pos_dev,
            num_nodes=n_nodes,
            num_neg_samples=train_pos_dev.shape[1] * args.negative_sample_multiplier,
        ).to(device)
        loss = model.recon_loss(z, train_pos_dev, neg_edge_index=neg_edges) + (1.0 / n_nodes) * model.kl_loss()
        loss.backward()
        optimizer.step()

        # Cheap diagnostic: AUC on the calibration half (still leakage-free as long as we don't use it for early stopping)
        if epoch == 1 or epoch % 10 == 0 or epoch == args.epochs:
            model.eval()
            with torch.no_grad():
                z_eval = model.encode(x_dev, full_edge_index_dev)
            cal_pairs = data.edge_index[:, torch.tensor(cal_global, dtype=torch.long)].to(device)
            cal_scores = _per_edge_score(model, z_eval, cal_pairs)
            cal_auc = _safe_auc(cal_labels_global, cal_scores)
            logger.info(f"  epoch {epoch:3d}  loss={loss.item():.4f}  cal_auc={cal_auc:.4f}")
            log_rows.append({"epoch": epoch, "loss": float(loss.item()), "cal_auc": cal_auc})
        else:
            log_rows.append({"epoch": epoch, "loss": float(loss.item()), "cal_auc": ""})

    t_train_total = time.time() - t_train_start
    logger.info(f"Training complete in {t_train_total:.1f}s on {device}")

    # Final eval
    model.eval()
    with torch.no_grad():
        z_final = model.encode(x_dev, full_edge_index_dev)
    cal_pairs = data.edge_index[:, torch.tensor(cal_global, dtype=torch.long)].to(device)
    eval_pairs = data.edge_index[:, torch.tensor(eval_global, dtype=torch.long)].to(device)
    cal_scores = _per_edge_score(model, z_final, cal_pairs)
    eval_scores = _per_edge_score(model, z_final, eval_pairs)
    eval_labels = data.y[eval_global].cpu().numpy()
    final_cal_auc = _safe_auc(cal_labels_global, cal_scores)
    final_eval_auc = _safe_auc(eval_labels, eval_scores)

    # Reference: unsupervised tabular baselines (from prior runs)
    reference_unsupervised = {
        "isolation_forest_lanl": 0.9098,
        "oneclass_svm_lanl": 0.667,
        "lof_lanl": 0.4925,
        "elliptic_envelope_lanl": 0.7741,
        "pca_reconstruction_lanl": 0.6672,
        "supervised_lr_on_5_features": 0.9733,
        "combined_graph_pipeline": 0.9544,
    }

    if args.output_dir is None:
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_dir = REPO_ROOT / "results" / ts / "vgae"
    else:
        out_dir = args.output_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "input_data": str(args.data.resolve()),
        "device": str(device),
        "config": {
            "hidden": args.hidden,
            "latent": args.latent,
            "lr": args.lr,
            "epochs": args.epochs,
            "holdout_frac": args.holdout_frac,
            "seed": args.seed,
            "negative_sample_multiplier": args.negative_sample_multiplier,
            "training_positives": args.training_positives,
        },
        "graph": {
            "n_nodes": int(n_nodes),
            "in_features": int(in_dim),
            "n_edges_full": int(n_edges),
            "n_edges_masked": int(data.mask.sum()),
            "n_redteam_total": int(data.y.sum()),
            "n_redteam_masked": int(data.y[data.mask].sum()),
        },
        "split": {
            "calibration_edges": int(len(cal_global)),
            "evaluation_edges": int(len(eval_global)),
            "calibration_redteam": n_cal_redteam,
            "evaluation_redteam": n_eval_redteam,
            "training_positives": int(train_pos_edges.shape[1]),
        },
        "training_seconds": float(t_train_total),
        "results": {
            "vgae_calibration_auc": final_cal_auc,
            "vgae_evaluation_auc": final_eval_auc,
            "overfit_gap_cal_minus_eval": final_cal_auc - final_eval_auc,
        },
        "reference_baselines": reference_unsupervised,
        "delta_vs_isolation_forest": final_eval_auc - reference_unsupervised["isolation_forest_lanl"],
        "delta_vs_supervised_lr": final_eval_auc - reference_unsupervised["supervised_lr_on_5_features"],
    }

    out_json = out_dir / "vgae_results.json"
    out_json.write_text(json.dumps(payload, indent=2))
    logger.info(f"Wrote {out_json}")

    out_csv = out_dir / "training_log.csv"
    with open(out_csv, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["epoch", "loss", "cal_auc"])
        writer.writeheader()
        for row in log_rows:
            writer.writerow(row)
    logger.info(f"Wrote {out_csv}")

    logger.info("=" * 70)
    logger.info("VGAE held-out result")
    logger.info(f"  Calibration AUC : {final_cal_auc:.6f}")
    logger.info(f"  Evaluation AUC  : {final_eval_auc:.6f}")
    logger.info(f"  Overfit gap     : {final_cal_auc - final_eval_auc:+.6f}")
    logger.info("  Reference (unsupervised tabular):")
    for k, v in reference_unsupervised.items():
        logger.info(f"    {k:35} {v:.4f}")
    logger.info(f"  Δ vs IsolationForest (best tabular unsup) : {payload['delta_vs_isolation_forest']:+.4f}")
    logger.info(f"  Δ vs supervised LR on 5 features          : {payload['delta_vs_supervised_lr']:+.4f}")
    logger.info("=" * 70)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
