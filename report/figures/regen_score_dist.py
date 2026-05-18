"""Regenerate score_distribution.png from the latest pipeline results."""

import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from pathlib import Path

plt.style.use("seaborn-v0_8-whitegrid")
plt.rcParams.update({
    "font.size": 11,
    "font.family": "sans-serif",
    "font.sans-serif": ["Helvetica", "Arial"],
    "axes.linewidth": 1.0,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
})

BASE = Path(__file__).resolve().parent.parent
RESULTS_DIR = BASE / "results/20260516_090835/LANL-2015/combined"
REDTEAM_DIR = BASE / "results/20260516_090835/redteam"
OUT = BASE.parent / "Paper/score_distribution.png"

# Load edge scores
scores_df = pd.read_csv(RESULTS_DIR / "edge_scores.csv")
scores = scores_df["score"].values

# Load graph edges to get src/dst
edges_df = pd.read_csv(RESULTS_DIR / "graph_edges.csv", usecols=["src", "dst"])

# Load redteam pairs
with open(REDTEAM_DIR / "redteam_pairs.json") as f:
    redteam_pairs = {(p["src"], p["dst"]) for p in json.load(f)}

# Label each edge
is_redteam = np.array([
    (s, d) in redteam_pairs
    for s, d in zip(edges_df["src"].astype(str).values, edges_df["dst"].astype(str).values)
])

# Filter out self-loops and user edges for cleaner display
edge_features = pd.read_csv(RESULTS_DIR / "edge_features.csv")
is_self_loop = edge_features["is_self_loop"].values if "is_self_loop" in edge_features else np.zeros(len(edge_features))
is_user_edge = edge_features["is_user_edge"].values if "is_user_edge" in edge_features else np.zeros(len(edge_features))
valid_mask = (is_self_loop == 0.0) & (is_user_edge == 0.0)

scores_valid = scores[valid_mask]
is_redteam_valid = is_redteam[valid_mask]

baseline_scores = scores_valid[~is_redteam_valid]
redteam_scores = scores_valid[is_redteam_valid]

threshold = np.percentile(scores_valid, 97)

print(f"Total valid edges: {len(scores_valid)}")
print(f"Baseline edges: {len(baseline_scores)}")
print(f"Red team edges: {len(redteam_scores)}")
print(f"Threshold (97th pct): {threshold:.4f}")
print(f"Score range: [{scores_valid.min():.3f}, {scores_valid.max():.3f}]")

# Create histogram
fig, ax = plt.subplots(figsize=(7.5, 4.5))

bins = np.linspace(scores_valid.min(), scores_valid.max(), 60)

ax.hist(baseline_scores, bins=bins, alpha=0.6, color="#2ecc71", label="Baseline events", log=True)
ax.hist(redteam_scores, bins=bins, alpha=0.6, color="#e74c3c", label="Red team events", log=True)

# KDE overlay
from scipy.stats import gaussian_kde
if len(baseline_scores) > 1:
    kde_base = gaussian_kde(baseline_scores, bw_method=0.05)
    x_base = np.linspace(scores_valid.min(), scores_valid.max(), 200)
    ax.plot(x_base, kde_base(x_base) * len(baseline_scores) * (bins[1] - bins[0]),
            color="#27ae60", linewidth=1.5, alpha=0.8)

if len(redteam_scores) > 1:
    kde_rt = gaussian_kde(redteam_scores, bw_method=0.05)
    x_rt = np.linspace(scores_valid.min(), scores_valid.max(), 200)
    ax.plot(x_rt, kde_rt(x_rt) * len(redteam_scores) * (bins[1] - bins[0]),
            color="#c0392b", linewidth=1.5, alpha=0.8)

ax.axvline(threshold, color="#f39c12", linestyle="--", linewidth=1.5, label=f"Threshold ({threshold:.2f})")

ax.set_xlabel("Anomaly Score")
ax.set_ylabel("Count (log scale)")
ax.set_title(f"Score range [{scores_valid.min():.3f}, {scores_valid.max():.3f}] | Baseline: {len(baseline_scores):,}  Red team: {len(redteam_scores)}")
ax.legend(frameon=True, loc="upper right")
ax.grid(True, alpha=0.3)

plt.tight_layout()
plt.savefig(OUT)
plt.close()
print(f"Saved {OUT}")
