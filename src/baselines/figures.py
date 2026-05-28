"""Baseline comparison figures generated inside a baseline run directory."""

from __future__ import annotations

import json
from math import pi
from pathlib import Path
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

VARIANTS = ("combined", "auth_only", "flow_only")
VARIANT_LABELS = {
    "combined": "Combined\n(Flow + Auth)",
    "auth_only": "Auth Only",
    "flow_only": "Flow Only",
}
METHODS = (
    ("graph_based", "Graph-based", "#2196F3"),
    ("one_class_svm", "One-Class SVM", "#FF9800"),
    ("isolation_forest", "Isolation Forest", "#F44336"),
)


def generate_baseline_figures(
    baseline_run_dir: Path,
    pipeline_results_dir: Path,
) -> Path:
    """Generate comparison figures under ``baseline_run_dir / 'figures'``."""
    output_dir = baseline_run_dir / "figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(baseline_run_dir / "summary.json") as f:
        summary = json.load(f)

    run_id = summary.get("run_id")
    if not isinstance(run_id, str):
        raise ValueError("summary.json missing string run_id")

    redteam_path = pipeline_results_dir / run_id / "redteam" / "redteam_pairs.json"
    with open(redteam_path) as f:
        num_redteam = len(json.load(f))

    all_data = _variant_methods(summary)
    variants = [variant for variant in VARIANTS if variant in all_data]
    methods = _available_methods(all_data)
    if not methods:
        raise ValueError("summary.json contains no supported methods")

    _plot_f1(output_dir, all_data, variants, methods)
    _plot_auc(output_dir, all_data, variants, methods)
    _plot_recall_fpr(output_dir, all_data, variants, methods)
    _plot_radar(output_dir, all_data, methods)
    _plot_detected_pairs(output_dir, all_data, variants, methods, num_redteam)

    return output_dir


def _metric(metrics: dict[str, Any], key: str) -> float:
    value = metrics.get(key, 0.0)
    return float(value) if isinstance(value, int | float) else 0.0


def _variant_methods(summary: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    raw = summary.get("per_variant_summary")
    if not isinstance(raw, dict):
        raise ValueError("summary.json missing per_variant_summary")

    all_data: dict[str, dict[str, dict[str, Any]]] = {}
    for variant in VARIANTS:
        variant_summary = raw.get(variant)
        if not isinstance(variant_summary, dict):
            continue

        all_data[variant] = {}
        for key, label, _color in METHODS:
            metrics = variant_summary.get(key)
            if isinstance(metrics, dict):
                all_data[variant][label] = metrics

    if not all_data:
        raise ValueError("summary.json contains no supported variant/method metrics")
    return all_data


def _available_methods(
    all_data: dict[str, dict[str, dict[str, Any]]],
) -> list[tuple[str, str]]:
    labels = {label for methods in all_data.values() for label in methods}
    return [(label, color) for _key, label, color in METHODS if label in labels]


def _values(
    all_data: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    method: str,
    metric: str,
) -> list[float]:
    return [_metric(all_data[variant].get(method, {}), metric) for variant in variants]


def _bar_geometry(method_count: int, variant_count: int) -> tuple[np.ndarray, float, np.ndarray]:
    x = np.arange(variant_count)
    width = min(0.8 / method_count, 0.25)
    offsets = (np.arange(method_count) - (method_count - 1) / 2) * width
    return x, width, offsets


def _plot_f1(
    output_dir: Path,
    all_data: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    methods: list[tuple[str, str]],
) -> None:
    x, width, offsets = _bar_geometry(len(methods), len(variants))
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, (method, color) in enumerate(methods):
        ax.bar(
            x + offsets[i],
            _values(all_data, variants, method, "f1"),
            width,
            label=method,
            color=color,
        )

    ax.set_xlabel("Data Variant", fontsize=12)
    ax.set_ylabel("F1 Score", fontsize=12)
    ax.set_title("F1 Score Comparison", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([VARIANT_LABELS[v] for v in variants])
    ax.legend(fontsize=10)
    ax.set_yscale("log")
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_f1_comparison.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_auc(
    output_dir: Path,
    all_data: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    methods: list[tuple[str, str]],
) -> None:
    x, width, offsets = _bar_geometry(len(methods), len(variants))
    fig, ax = plt.subplots(figsize=(10, 6))
    for i, (method, color) in enumerate(methods):
        ax.bar(
            x + offsets[i],
            _values(all_data, variants, method, "auc"),
            width,
            label=method,
            color=color,
        )

    ax.set_xlabel("Data Variant", fontsize=12)
    ax.set_ylabel("ROC AUC", fontsize=12)
    ax.set_title("ROC AUC Comparison", fontsize=14, fontweight="bold")
    ax.set_xticks(x)
    ax.set_xticklabels([VARIANT_LABELS[v] for v in variants])
    ax.legend(fontsize=10)
    ax.set_ylim(0.4, 1.05)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_auc_comparison.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_recall_fpr(
    output_dir: Path,
    all_data: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    methods: list[tuple[str, str]],
) -> None:
    fig, ax = plt.subplots(figsize=(8, 6))
    for method, color in methods:
        recalls = _values(all_data, variants, method, "recall")
        fprs = _values(all_data, variants, method, "fpr")
        ax.scatter(fprs, recalls, s=150, c=color, label=method, marker="o", zorder=5)
        for i, variant in enumerate(variants):
            ax.annotate(
                variant.replace("_", "\n"),
                (fprs[i], recalls[i]),
                textcoords="offset points",
                xytext=(8, 5),
                fontsize=8,
            )

    ax.set_xlabel("False Positive Rate", fontsize=12)
    ax.set_ylabel("Recall", fontsize=12)
    ax.set_title("Recall vs FPR", fontsize=14, fontweight="bold")
    ax.legend(fontsize=10)
    ax.grid(alpha=0.3)
    ax.set_xlim(-0.005, 0.11)
    ax.set_ylim(-0.01, 1.05)
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_recall_fpr_scatter.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_radar(
    output_dir: Path,
    all_data: dict[str, dict[str, dict[str, Any]]],
    methods: list[tuple[str, str]],
) -> None:
    if "combined" not in all_data:
        return

    categories = ["Recall", "FPR", "F1", "Precision", "AUC"]
    angles = [n / float(len(categories)) * 2 * pi for n in range(len(categories))]
    angles += angles[:1]

    fig, ax = plt.subplots(figsize=(8, 8), subplot_kw={"projection": "polar"})
    for method, color in methods:
        values = [
            _metric(all_data["combined"].get(method, {}), "recall"),
            _metric(all_data["combined"].get(method, {}), "fpr"),
            _metric(all_data["combined"].get(method, {}), "f1"),
            _metric(all_data["combined"].get(method, {}), "precision"),
            _metric(all_data["combined"].get(method, {}), "auc"),
        ]
        values += values[:1]
        ax.plot(angles, values, "o-", linewidth=2, label=method, color=color)
        ax.fill(angles, values, alpha=0.1, color=color)

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(categories, fontsize=11)
    ax.set_ylim(0, 1)
    ax.set_title("Combined Variant", fontsize=14, fontweight="bold", pad=20)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1), fontsize=10)
    ax.grid(alpha=0.3)
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_radar_combined.png", dpi=300, bbox_inches="tight")
    plt.close(fig)


def _plot_detected_pairs(
    output_dir: Path,
    all_data: dict[str, dict[str, dict[str, Any]]],
    variants: list[str],
    methods: list[tuple[str, str]],
    num_redteam: int,
) -> None:
    fig, axes = plt.subplots(1, len(variants), figsize=(5 * len(variants), 5), squeeze=False)
    for i, variant in enumerate(variants):
        ax = axes[0][i]
        method_names = [method for method, _color in methods]
        detected_counts = [
            int(_metric(all_data[variant].get(method, {}), "num_detected_pairs"))
            for method in method_names
        ]

        ax.bar(method_names, detected_counts, color=[color for _method, color in methods])
        ax.axhline(
            y=num_redteam,
            color="gray",
            linestyle="--",
            alpha=0.7,
            label=f"Total red-team ({num_redteam})",
        )
        ax.set_title(variant.replace("_", " ").title(), fontsize=12)
        ax.set_xlabel("Detection Method", fontsize=11)
        ax.set_ylabel("Detected Pairs", fontsize=11)
        ax.tick_params(axis="x", rotation=45)
        if i == 0:
            ax.legend(fontsize=9)

    plt.suptitle("Detected Red-Team Pairs by Method", fontsize=14, fontweight="bold")
    plt.tight_layout()
    fig.savefig(output_dir / "baseline_detected_pairs.png", dpi=300, bbox_inches="tight")
    plt.close(fig)
