"""Generate baseline comparison figures for the report."""

import argparse
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description="Generate baseline comparison figures")
    parser.add_argument("--baseline-dir", default="baseline_results",
                        help="Base directory for baseline results")
    parser.add_argument("--run-id", default=None,
                        help="Baseline run ID (timestamp). Auto-discovers latest if not specified.")
    parser.add_argument("--results-dir", default="results",
                        help="Base directory for pipeline results")
    parser.add_argument("--output-dir", default="Graph-based-Threat-Detection/figures",
                        help="Output directory for figures")
    return parser.parse_args()


def find_latest_run(baseline_dir: Path) -> str:
    """Find the latest timestamp directory in baseline_dir."""
    dirs = sorted([d.name for d in baseline_dir.iterdir() if d.is_dir()])
    if not dirs:
        raise FileNotFoundError(f"No run directories found in {baseline_dir}")
    return dirs[-1]


def main():
    args = parse_args()

    baseline_dir = Path(args.baseline_dir)
    output_dir = Path(args.output_dir)
    results_base = Path(args.results_dir)

    # Resolve run ID — auto-discover latest if not specified
    run_id = args.run_id
    if run_id is None:
        run_id = find_latest_run(baseline_dir)

    baseline_path = baseline_dir / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    # Load summary.json
    with open(baseline_path / "summary.json") as f:
        summary = json.load(f)

    # Derive pipeline results dir from summary's run_id
    results_dir = results_base / summary["run_id"]

    variants = ["combined", "auth_only", "flow_only"]
    methods = ["Graph-based", "SVC (supervised)", "One-Class SVM", "Isolation Forest"]
    metrics_keys = ["recall", "fpr", "f1", "precision", "auc"]
    metric_labels = ["Recall", "False Positive Rate", "F1 Score", "Precision", "ROC AUC"]

    # Build data matrix from summary.json
    method_key_map = {
        "Graph-based": "graph_based",
        "SVC (supervised)": "svc",
        "One-Class SVM": "one_class_svm",
        "Isolation Forest": "isolation_forest",
    }

    all_data = {}
    for v in variants:
        all_data[v] = {}
        for method, key in method_key_map.items():
            all_data[v][method] = summary["per_variant_summary"][v][key]

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
    plt.savefig(output_dir / "baseline_f1_comparison.png", dpi=300, bbox_inches="tight")
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
    plt.savefig(output_dir / "baseline_auc_comparison.png", dpi=300, bbox_inches="tight")
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
    plt.savefig(output_dir / "baseline_recall_fpr_scatter.png", dpi=300, bbox_inches="tight")
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
    plt.savefig(output_dir / "baseline_radar_combined.png", dpi=300, bbox_inches="tight")
    plt.close()

    # ============================================================
    # Figure 5: Stacked bar - detected pairs breakdown
    # ============================================================
    fig, axes = plt.subplots(1, 3, figsize=(14, 5))

    with open(results_dir / "redteam" / "redteam_pairs.json") as f:
        redteam = json.load(f)
    num_redteam = len(redteam)

    for idx, v in enumerate(variants):
        ax = axes[idx]

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
    plt.savefig(output_dir / "baseline_detected_pairs.png", dpi=300, bbox_inches="tight")
    plt.close()

    print("All figures saved to:", output_dir)


if __name__ == "__main__":
    main()
