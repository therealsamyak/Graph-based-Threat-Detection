"""Style configuration and shared plotting constants for figures."""

from __future__ import annotations

import logging

import matplotlib.pyplot as plt

from src.visualization.style import _apply_style, _save_fig

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

PAPER_DPI = 300

PAPER_CONFIG = {
    "font.size": 18,
    "axes.titlesize": 22,
    "axes.labelsize": 20,
    "xtick.labelsize": 17,
    "ytick.labelsize": 17,
    "legend.fontsize": 17,
    "figure.figsize": (12, 7),
    "savefig.dpi": PAPER_DPI,
}

# Method and variant ordering
VARIANT_ORDER = ["combined", "auth_only", "flow_only"]
METHOD_ORDER = ["graph_based", "one_class_svm", "isolation_forest"]

VARIANT_LABELS = {
    "combined": "Combined",
    "auth_only": "Auth Only",
    "flow_only": "Flow Only",
}

# Display names for methods (no variant suffix)
METHOD_DISPLAY_NAMES = {
    "graph_based": "Graph-based",
    "one_class_svm": "One-Class SVM",
    "isolation_forest": "Isolation Forest",
}

# Base colors for methods
BASE_METHOD_COLORS = {
    "graph_based": "#2196F3",
    "one_class_svm": "#9C27B0",
    "isolation_forest": "#F44336",
}

# Alpha values for variants
VARIANT_ALPHAS = {
    "combined": 0.9,
    "auth_only": 0.7,
    "flow_only": 0.5,
}

# Build 9 colors keyed by (method, variant) tuples
METHOD_COLORS: dict[tuple[str, str], str] = {}
for method in METHOD_ORDER:
    for variant in VARIANT_ORDER:
        base_color = BASE_METHOD_COLORS[method]
        METHOD_COLORS[(method, variant)] = base_color

# Build 9 labels keyed by (method, variant) tuples
METHOD_LABELS: dict[tuple[str, str], str] = {}
for method in METHOD_ORDER:
    for variant in VARIANT_ORDER:
        variant_label = VARIANT_LABELS[variant]
        method_display = {
            "graph_based": "Graph-based",
            "one_class_svm": "One-Class SVM",
            "isolation_forest": "Isolation Forest",
        }[method]
        METHOD_LABELS[(method, variant)] = f"{method_display} ({variant_label})"


def get_method_color(method: str, variant: str) -> str:
    """Get color for a specific (method, variant) combination."""
    return METHOD_COLORS[(method, variant)]


def get_method_label(method: str, variant: str) -> str:
    """Get display label for a specific (method, variant) combination."""
    return METHOD_LABELS[(method, variant)]


def iter_method_variants():
    """Yield (method, variant, color, label) tuples grouped by variant."""
    for variant in VARIANT_ORDER:
        for method in METHOD_ORDER:
            yield (method, variant, METHOD_COLORS[(method, variant)], METHOD_LABELS[(method, variant)])


def apply_paper_style() -> None:
    _apply_style()
    plt.rcParams.update(PAPER_CONFIG)


def save_placeholder_figure(output_path: str, title: str, reason: str) -> None:
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.axis("off")
    ax.text(0.5, 0.62, title, ha="center", va="center", fontsize=22, fontweight="bold")
    ax.text(0.5, 0.42, "Skipped gracefully", ha="center", va="center", fontsize=18)
    ax.text(0.5, 0.28, reason, ha="center", va="center", fontsize=15, color="#666666", wrap=True)
    _save_fig(fig, output_path)
