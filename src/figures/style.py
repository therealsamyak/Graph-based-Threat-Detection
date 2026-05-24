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
    "font.size": 12,
    "axes.titlesize": 14,
    "axes.labelsize": 12,
    "xtick.labelsize": 10,
    "ytick.labelsize": 10,
    "legend.fontsize": 10,
    "figure.figsize": (10, 6),
    "savefig.dpi": PAPER_DPI,
}

METHOD_COLORS = {
    "combined": "#2196F3",
    "auth_only": "#4CAF50",
    "flow_only": "#FF9800",
    "oneclass_svm": "#9C27B0",
    "isolation_forest": "#F44336",
}

METHOD_LABELS = {
    "combined": "Graph (Combined)",
    "auth_only": "Graph (Auth Only)",
    "flow_only": "Graph (Flow Only)",
    "oneclass_svm": "One-Class SVM",
    "isolation_forest": "Isolation Forest",
}


def apply_paper_style() -> None:
    _apply_style()
    plt.rcParams.update(PAPER_CONFIG)
