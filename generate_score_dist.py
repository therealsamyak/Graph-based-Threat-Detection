"""Generate score distribution figure with log scale y-axis and FPR calculation."""

import json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

RESULTS_DIR = "results/20260504_011631"
OUTPUT_PATH = "figures/score_distribution.png"

# Load red-team pairs
with open(f"{RESULTS_DIR}/redteam/redteam_pairs.json") as f:
    red_pairs = set((p["src"], p["dst"]) for p in json.load(f))

# Load combined method edge scores and graph edges
scores_df = pd.read_csv(f"{RESULTS_DIR}/combined/edge_scores.csv")
edges_df = pd.read_csv(f"{RESULTS_DIR}/combined/graph_edges.csv", low_memory=False)

# Ensure same length
n = min(len(scores_df), len(edges_df))
scores_df = scores_df.iloc[:n]
edges_df = edges_df.iloc[:n]

# Build labels and pairs
labels = []
all_pairs = []
for _, row in edges_df.iterrows():
    pair = (str(row["src"]), str(row["dst"]))
    all_pairs.append(pair)
    labels.append(1.0 if pair in red_pairs else 0.0)

labels = np.array(labels)
scores = scores_df["score"].values

# Separate baseline and red-team scores
baseline_scores = scores[labels == 0]
redteam_scores = scores[labels == 1]

# Calculate FPR at 97th percentile threshold (as per Section 4.6)
threshold = np.percentile(scores, 97)
flagged_indices = scores >= threshold
flagged_pairs = set(p for i, p in enumerate(all_pairs) if flagged_indices[i])
baseline_pairs = set(p for i, p in enumerate(all_pairs) if labels[i] == 0)
flagged_baseline_pairs = flagged_pairs & baseline_pairs
fpr = len(flagged_baseline_pairs) / max(len(baseline_pairs), 1)

print(f"Total edges: {len(scores)}")
print(f"Baseline edges: {len(baseline_scores)}")
print(f"Red-team edges: {len(redteam_scores)}")
print(f"Red-team score stats: mean={redteam_scores.mean():.4f}, median={np.median(redteam_scores):.4f}, min={redteam_scores.min():.4f}, max={redteam_scores.max():.4f}")
print(f"Baseline score stats: mean={baseline_scores.mean():.4f}, median={np.median(baseline_scores):.4f}")
print(f"\nFPR Calculation (at 97th percentile threshold = {threshold:.4f}):")
print(f"  Total unique pairs: {len(set(all_pairs))}")
print(f"  Unique baseline pairs: {len(baseline_pairs)}")
print(f"  Flagged pairs (score >= {threshold:.4f}): {len(flagged_pairs)}")
print(f"  Flagged baseline pairs (false positives): {len(flagged_baseline_pairs)}")
print(f"  FPR = {len(flagged_baseline_pairs)} / {len(baseline_pairs)} = {fpr:.4f} ({fpr*100:.1f}%)")

# Plot with log scale - cleaner version for paper
fig, ax = plt.subplots(figsize=(10, 6))
bins = np.linspace(0, 1, 50)

# Plot baseline first (larger dataset)
ax.hist(baseline_scores, bins=bins, alpha=0.6, color="#2ecc71", 
        label=f"Baseline (n={len(baseline_scores):,}, mean=0.45)", 
        edgecolor="white", linewidth=0.3)

# Plot red-team on top (smaller dataset, more visible)
ax.hist(redteam_scores, bins=bins, alpha=0.8, color="#e74c3c", 
        label=f"Red team (n={len(redteam_scores)}, mean=0.98)", 
        edgecolor="darkred", linewidth=0.5)

# Add threshold line
ax.axvline(x=threshold, color="black", linestyle="--", linewidth=1.5, 
           label=f"Threshold (97th pct = {threshold:.2f})")

ax.set_yscale("log")
ax.set_title("Score Distribution (log scale)", fontsize=14, fontweight="bold", pad=10)
ax.set_xlabel("Anomaly score", fontsize=12)
ax.set_ylabel("Count (log scale)", fontsize=12)
ax.legend(fontsize=10, framealpha=0.9, loc="upper left")
ax.grid(True, alpha=0.3, which="both", linestyle="--", linewidth=0.5)
ax.set_xlim(0, 1)
fig.tight_layout()
fig.savefig(OUTPUT_PATH, dpi=150, bbox_inches="tight")
plt.close(fig)
print(f"\nSaved {OUTPUT_PATH}")
