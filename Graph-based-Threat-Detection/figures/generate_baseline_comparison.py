"""Generate baseline comparison figures for the report."""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import os

# Load baseline results
BASELINE_DIR = "baseline_results/20260523_140723"
RESULTS_DIR = "results/20260520_110758"
OUTPUT_DIR = "Graph-based-Threat-Detection/figures"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# Load baseline per-variant results
with open(os.path.join(BASELINE_DIR, "per_variant_results.json")) as f:
    baseline_data = json.load(f)

# Load graph-based results from pipeline
def load_graph_results(variant):
    """Load graph-based results from pipeline output."""
    detected_path = os.path.join(RESULTS_DIR, "LANL-2015", variant, "detected_redteam_pairs.json")
    with open(detected_path) as f:
        detected = json.load(f)
    # Load edge scores to get total edges
    import csv
    edge_features_path = os.path.join(RESULTS_DIR, "LANL-2015", variant, "edge_features.csv")
    total_edges = 0
    with open(edge_features_path) as f:
        reader = csv.reader(f)
        next(reader)  # skip header
        for _ in reader:
            total_edges += 1
    return len(detected), total_edges

variants = ["combined", "auth_only", "flow_only"]
methods = ["Graph-based", "SVC (supervised)", "One-Class SVM", "Isolation Forest"]
metrics_keys = ["recall", "fpr", "f1", "precision", "auc"]
metric_labels = ["Recall", "False Positive Rate", "F1 Score", "Precision", "ROC AUC"]

# Build data matrix: variants x methods x metrics
data = {}
for v in variants:
    data[v] = {}
    # Graph-based: compute from detected pairs
    # We need to load the redteam pairs to compute recall
    with open(os.path.join(RESULTS_DIR, "redteam", "redteam_pairs.json")) as f:
        redteam_pairs = json.load(f)
    num_redteam = len(redteam_pairs)

    with open(os.path.join(RESULTS_DIR, "LANL-2015", v, "detected_redteam_pairs.json")) as f:
        detected = json.load(f)
    num_detected = len(detected)

    # Load edge features to get total valid edges
    import csv
    total_edges = 0
    with open(os.path.join(RESULTS_DIR, "LANL-2015", v, "edge_features.csv")) as f:
        reader = csv.reader(f)
        next(reader)
        for row in reader:
            total_edges += 1

    # Load graph features to get the actual metrics from the pipeline
    # We'll use the comparison table as reference
    recall = num_detected / num_redteam if num_redteam > 0 else 0
    # Approximate FPR from the pipeline - we'll use known values
    # For now, load from the baseline comparison which already has graph-based values
    data[v]["Graph-based"] = {}

# Actually, let's load the graph-based metrics from the baseline comparison table
# which already loaded them correctly
with open(os.path.join(BASELINE_DIR, "comparison_table.md")) as f:
    comparison_md = f.read()

# Parse the comparison table
import re
graph_metrics = {}
for v in variants:
    graph_metrics[v] = {}
    # Find the section for this variant
    pattern = f"### {v}\n\n\\| Method \\| Recall \\| FPR \\| F1 \\| Precision \\| AUC \\|\n\\|-+"
    match = re.search(pattern, comparison_md)
    if match:
        # Get the next line (graph-based row)
        start = match.end()
        next_line = comparison_md[start:start+200]
        # Parse: | Graph-based | 0.9448 | 0.0295 | 0.0371 | 0.0189 | 0.9756 |
        row_match = re.search(r"\| Graph-based \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \| ([\d.]+) \|", next_line)
        if row_match:
            graph_metrics[v]["recall"] = float(row_match.group(1))
            graph_metrics[v]["fpr"] = float(row_match.group(2))
            graph_metrics[v]["f1"] = float(row_match.group(3))
            graph_metrics[v]["precision"] = float(row_match.group(4))
            graph_metrics[v]["auc"] = float(row_match.group(5))

# Now build full data
all_data = {}
for v in variants:
    all_data[v] = {}
    all_data[v]["Graph-based"] = graph_metrics[v]
    all_data[v]["SVC (supervised)"] = baseline_data[v]["svc"]["pair_metrics"]
    all_data[v]["One-Class SVM"] = baseline_data[v]["one_class_svm"]["pair_metrics"]
    all_data[v]["Isolation Forest"] = baseline_data[v]["isolation_forest"]["pair_metrics"]

# ============================================================
# Figure 1: Grouped bar chart - F1 Score per variant
# ============================================================
fig, ax = plt.subplots(figsize=(10, 6))
x = np.arange(len(variants))
width = 0.2
colors = {"Graph-based": "#2196F3", "SVC (supervised)": "#4CAF50",
          "One-Class SVM": "#FF9800", "Isolation Forest": "#F44336"}

for i, method in enumerate(methods):
    values = [all_data[v][method]["f1"] for v in variants]
    ax.bar(x + i * width, values, width, label=method, color=colors[method])

ax.set_xlabel("Data Variant", fontsize=12)
ax.set_ylabel("F1 Score", fontsize=12)
ax.set_title("F1 Score Comparison: Graph-based vs Baseline Methods", fontsize=14, fontweight="bold")
ax.set_xticks(x + width * 1.5)
ax.set_xticklabels(["Combined\n(Flow + Auth)", "Auth Only", "Flow Only"])
ax.legend(fontsize=10)
ax.set_yscale("log")
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "baseline_f1_comparison.png"), dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# Figure 2: Grouped bar chart - ROC AUC per variant
# ============================================================
fig, ax = plt.subplots(figsize=(10, 6))
for i, method in enumerate(methods):
    values = [all_data[v][method]["auc"] for v in variants]
    ax.bar(x + i * width, values, width, label=method, color=colors[method])

ax.set_xlabel("Data Variant", fontsize=12)
ax.set_ylabel("ROC AUC", fontsize=12)
ax.set_title("ROC AUC Comparison: Graph-based vs Baseline Methods", fontsize=14, fontweight="bold")
ax.set_xticks(x + width * 1.5)
ax.set_xticklabels(["Combined\n(Flow + Auth)", "Auth Only", "Flow Only"])
ax.legend(fontsize=10)
ax.set_ylim(0.4, 1.05)
ax.grid(axis="y", alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "baseline_auc_comparison.png"), dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# Figure 3: Recall vs FPR scatter (detection quality)
# ============================================================
fig, ax = plt.subplots(figsize=(8, 6))
for method in methods:
    recalls = [all_data[v][method]["recall"] for v in variants]
    fprs = [all_data[v][method]["fpr"] for v in variants]
    ax.scatter(fprs, recalls, s=150, c=colors[method], label=method, marker="o", zorder=5)
    # Add variant labels
    for j, v in enumerate(variants):
        ax.annotate(v.replace("_", "\n"), (fprs[j], recalls[j]),
                   textcoords="offset points", xytext=(8, 5), fontsize=8)

# Ideal: top-left corner
ax.set_xlabel("False Positive Rate", fontsize=12)
ax.set_ylabel("Recall", fontsize=12)
ax.set_title("Recall vs FPR: Detection Quality by Method", fontsize=14, fontweight="bold")
ax.legend(fontsize=10)
ax.grid(alpha=0.3)
ax.set_xlim(-0.005, 0.11)
ax.set_ylim(-0.01, 1.05)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "baseline_recall_fpr_scatter.png"), dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# Figure 4: Radar chart for combined variant
# ============================================================
from math import pi

categories = ["Recall", "FPR", "F1", "Precision", "AUC"]
N = len(categories)

# What angle each axis will be at
angles = [n / float(N) * 2 * pi for n in range(N)]
angles += angles[:1]  # close the loop

fig, ax = plt.subplots(figsize=(8, 8), subplot_kw=dict(projection="polar"))

for method in methods:
    v = "combined"
    values = [
        all_data[v][method]["recall"],
        all_data[v][method]["fpr"],
        all_data[v][method]["f1"],
        all_data[v][method]["precision"],
        all_data[v][method]["auc"]
    ]
    values += values[:1]  # close the loop
    ax.plot(angles, values, "o-", linewidth=2, label=method, color=colors[method])
    ax.fill(angles, values, alpha=0.1, color=colors[method])

ax.set_xticks(angles[:-1])
ax.set_xticklabels(categories, fontsize=11)
ax.set_ylim(0, 1)
ax.set_title("Radar Chart: Combined Variant (Flow + Auth)", fontsize=14, fontweight="bold", pad=20)
ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
ax.grid(alpha=0.3)
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "baseline_radar_combined.png"), dpi=300, bbox_inches="tight")
plt.close()

# ============================================================
# Figure 5: Stacked bar - detected pairs breakdown
# ============================================================
fig, axes = plt.subplots(1, 3, figsize=(14, 5))

for idx, v in enumerate(variants):
    ax = axes[idx]
    with open(os.path.join(RESULTS_DIR, "redteam", "redteam_pairs.json")) as f:
        redteam = json.load(f)
    num_redteam = len(redteam)

    detected_counts = []
    for method in methods:
        detected_counts.append(all_data[v][method].get("num_detected_pairs", 0))

    bars = ax.bar(methods, detected_counts, color=[colors[m] for m in methods])
    ax.axhline(y=num_redteam, color="gray", linestyle="--", alpha=0.7, label=f"Total red-team ({num_redteam})")
    ax.set_title(v.replace("_", " ").title(), fontsize=12)
    ax.set_ylabel("Detected Pairs", fontsize=11)
    ax.tick_params(axis="x", rotation=45)
    if idx == 0:
        ax.legend(fontsize=9)

plt.suptitle("Detected Red-Team Pairs by Method", fontsize=14, fontweight="bold")
plt.tight_layout()
plt.savefig(os.path.join(OUTPUT_DIR, "baseline_detected_pairs.png"), dpi=300, bbox_inches="tight")
plt.close()

print("All figures saved to:", OUTPUT_DIR)
