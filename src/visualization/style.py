"""Shared visualization constants and helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

try:
    from matplotlib.dates import DateFormatter as _DateFormatter
    _HAS_DATEFORMATTER = True
except ImportError:
    _DateFormatter = None
    _HAS_DATEFORMATTER = False

try:
    from scipy.stats import gaussian_kde as _gaussian_kde
    _HAS_SCIPY_KDE = True
except ImportError:
    _gaussian_kde = None
    _HAS_SCIPY_KDE = False

PALETTE = ["#2ecc71", "#e74c3c", "#3498db", "#f39c12", "#9b59b6", "#1abc9c", "#e67e22"]
LINE_STYLES = ["-", "--", "-.", ":", "-", "--", "-."]
BG_COLOR = "#fdfdfd"
FIG_SIZE = (10, 6)
DPI = 150
TITLE_FS = 14
LABEL_FS = 12

NODE_COLORS = {"computer": "#3498db", "user": "#2ecc71"}
EDGE_COLORS = {"auth": "#3498db", "flow": "#e74c3c"}


def _apply_style() -> None:
    """Apply a clean matplotlib style with fallback."""
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            pass


def _save_fig(fig, output_path: str) -> None:
    """Save figure and close."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=DPI, bbox_inches="tight", facecolor=BG_COLOR)
    plt.close(fig)
