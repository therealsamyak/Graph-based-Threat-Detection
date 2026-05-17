"""Generate publication-quality figures for the Results section."""

import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

# Use a clean, academic style
plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "font.size": 11,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial"],
    "axes.linewidth": 1.0,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.transparent": False,
})

OUT = Path(__file__).parent

# ── Figure 1: Feature Importance (Top 10 features by AUC) ──────────────────
def plot_feature_importance():
    features = [
        ("is_ntlm", 0.9327),
        ("source_fan_out", 0.9060),
        ("dst_in_degree", 0.8189),
        ("dst_fan_out_ratio", 0.8178),
        ("is_network_logon", 0.8170),
        ("dst_total_degree", 0.8122),
        ("edge_rarity", 0.8085),
        ("weight_norm", 0.8085),
        ("dst_inter_arrival_std", 0.7852),
        ("src_inter_arrival_mean", 0.7800),
    ]
    names = [f[0] for f in features]
    aucs = [f[1] for f in features]

    fig, ax = plt.subplots(figsize=(6.5, 4.0))
    colors = plt.cm.Blues(np.linspace(0.4, 0.85, len(names)))[::-1]
    bars = ax.barh(names[::-1], aucs[::-1], color=colors, edgecolor="white", height=0.6)

    for bar, auc in zip(bars, aucs[::-1]):
        ax.text(bar.get_width() + 0.005, bar.get_y() + bar.get_height() / 2,
                f"{auc:.4f}", va="center", fontsize=9, fontweight="medium")

    ax.set_xlim(0.7, 1.0)
    ax.set_xlabel("Individual Feature AUC")
    ax.set_title("Top 10 Edge Features by Discriminative Power (AUC)", fontweight="bold", pad=12)
    ax.axvline(0.5, color="gray", linestyle="--", linewidth=0.5, alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT / "feature_importance.png")
    plt.close()
    print(f"Saved {OUT / 'feature_importance.png'}")


# ── Figure 2: Tabular vs Graph Ablation ────────────────────────────────────
def plot_ablation():
    sets = ["Pure Tabular\n(9 features)", "Graph-Derived\n(17 features)", "Combined\n(26 features)"]
    aucs = [0.9562, 0.9891, 0.9922]

    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    colors = ["#4a90d9", "#e74c3c", "#27ae60"]
    bars = ax.bar(sets, aucs, color=colors, edgecolor="white", width=0.6)

    for bar, auc in zip(bars, aucs):
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.001,
                f"{auc:.4f}", ha="center", fontsize=11, fontweight="bold")

    ax.set_ylim(0.94, 1.0)
    ax.set_ylabel("Evaluation AUC")
    ax.set_title("Tabular vs. Graph Feature Ablation", fontweight="bold", pad=12)
    ax.axhline(0.9562, color="#4a90d9", linestyle="--", linewidth=0.7, alpha=0.5)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT / "ablation_comparison.png")
    plt.close()
    print(f"Saved {OUT / 'ablation_comparison.png'}")


# ── Figure 3: Graph Feature Sweep ──────────────────────────────────────────
def plot_feature_sweep():
    groups = [
        "Base\n(5 features)",
        "+ PageRank",
        "+ Personalized\nPageRank",
        "+ k-core",
        "+ Community",
        "+ Similarity",
        "All\nCombined",
    ]
    aucs = [0.9733, 0.9734, 0.9956, 0.9771, 0.9781, 0.9733, 0.9948]
    deltas = [0.0, 0.0002, 0.0224, 0.0039, 0.0048, 0.0001, 0.0215]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4.0), gridspec_kw={"width_ratios": [1, 1]})

    # Left: AUC values
    colors = ["#95a5a6"] * len(groups)
    colors[2] = "#e74c3c"  # Personalized PageRank
    colors[6] = "#27ae60"  # All Combined
    bars1 = ax1.bar(groups, aucs, color=colors, edgecolor="white", width=0.55)
    for bar, auc in zip(bars1, aucs):
        ax1.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0005,
                 f"{auc:.4f}", ha="center", fontsize=9, fontweight="medium")
    ax1.set_ylim(0.97, 1.0)
    ax1.set_ylabel("Evaluation AUC")
    ax1.set_title("Eval AUC by Feature Group", fontweight="bold", fontsize=11)
    ax1.spines["top"].set_visible(False)
    ax1.spines["right"].set_visible(False)
    ax1.tick_params(axis="x", rotation=0)

    # Right: Delta vs base
    colors2 = ["#95a5a6"] * len(groups)
    colors2[2] = "#e74c3c"
    colors2[6] = "#27ae60"
    bars2 = ax2.bar(groups, deltas, color=colors2, edgecolor="white", width=0.55)
    for bar, d in zip(bars2, deltas):
        label = f"+{d:.4f}" if d > 0 else "—"
        ax2.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.0002,
                 label, ha="center", fontsize=9, fontweight="medium")
    ax2.set_ylim(0, 0.025)
    ax2.set_ylabel("Δ AUC vs. Base")
    ax2.set_title("Incremental Gain over Base", fontweight="bold", fontsize=11)
    ax2.spines["top"].set_visible(False)
    ax2.spines["right"].set_visible(False)
    ax2.tick_params(axis="x", rotation=0)

    plt.suptitle("Graph Feature Sweep — Incremental AUC Gains", fontweight="bold", fontsize=13, y=1.02)
    plt.tight_layout()
    plt.savefig(OUT / "graph_feature_sweep.png")
    plt.close()
    print(f"Saved {OUT / 'graph_feature_sweep.png'}")


# ── Figure 4: Weight Optimization Comparison ───────────────────────────────
def plot_weight_optimization():
    methods = ["Equal Weights", "Nelder-Mead\nOptimizer", "Logistic\nRegression"]
    cal_auc = [0.1979, 0.9689, 0.9738]
    eval_auc = [0.1979, 0.9681, 0.9733]

    x = np.arange(len(methods))
    width = 0.3

    fig, ax = plt.subplots(figsize=(5.5, 4.0))
    bars1 = ax.bar(x - width / 2, cal_auc, width, label="Calibration AUC", color="#3498db", edgecolor="white")
    bars2 = ax.bar(x + width / 2, eval_auc, width, label="Evaluation AUC", color="#e74c3c", edgecolor="white")

    for bar in bars1:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{bar.get_height():.4f}", ha="center", fontsize=9, fontweight="medium")
    for bar in bars2:
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.01,
                f"{bar.get_height():.4f}", ha="center", fontsize=9, fontweight="medium")

    ax.set_xticks(x)
    ax.set_xticklabels(methods)
    ax.set_ylabel("AUC")
    ax.set_title("Weight Optimization: Calibration vs. Evaluation", fontweight="bold", pad=12)
    ax.legend(frameon=False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(OUT / "weight_optimization.png")
    plt.close()
    print(f"Saved {OUT / 'weight_optimization.png'}")


if __name__ == "__main__":
    plot_feature_importance()
    plot_ablation()
    plot_feature_sweep()
    plot_weight_optimization()
    print("All figures generated.")
