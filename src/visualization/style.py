"""Shared visualization constants and helpers."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

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
FIG_SIZE = (12, 7)
DPI = 300
TITLE_FS = 16
LABEL_FS = 14

NODE_COLORS = {"computer": "#3498db", "user": "#2ecc71"}
EDGE_COLORS = {"auth": "#3498db", "flow": "#e74c3c"}


def _smart_legend_loc(ax, preferred: str | None = None) -> dict:
    """Return legend kwargs placing the legend inside the least-cluttered corner.

    Analyzes data density in four quadrants to find the emptiest corner,
    weighting bar-top regions more heavily since those are the visually
    important parts.  Always returns a legend with a white background and
    visible border so it remains readable even when overlapping data.
    """
    import numpy as np

    _LOC_QUADRANT = {
        "upper right": (0.5, 1.0, 0.5, 1.0),
        "upper left": (0.0, 0.5, 0.5, 1.0),
        "lower right": (0.5, 1.0, 0.0, 0.5),
        "lower left": (0.0, 0.5, 0.0, 0.5),
    }

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    x_range = xlim[1] - xlim[0] if xlim[1] != xlim[0] else 1.0
    y_range = ylim[1] - ylim[0] if ylim[1] != ylim[0] else 1.0

    xs: list[float] = []
    ys: list[float] = []
    weights: list[float] = []

    for line in ax.get_lines():
        xdata = line.get_xdata()
        ydata = line.get_ydata()
        if len(xdata) > 0:
            xs.extend(xdata)
            ys.extend(ydata)
            weights.extend([1.0] * len(xdata))
    for coll in ax.collections:
        offsets = coll.get_offsets()
        if len(offsets) > 0:
            xs.extend(offsets[:, 0].tolist())
            ys.extend(offsets[:, 1].tolist())
            weights.extend([1.0] * len(offsets))
    for patch in ax.patches:
        try:
            bx = patch.get_x()
            by = patch.get_y()
            bw = patch.get_width()
            bh = patch.get_height()
            # For bars: place weighted points at the TOP of the bar
            # since that's the visually important region (the value).
            # Also add a few points along the top edge for width coverage.
            n_pts = max(3, int(bw / (x_range / 20)) + 1)
            for i in range(n_pts):
                frac = i / max(n_pts - 1, 1)
                xs.append(bx + bw * frac)
                ys.append(by + bh)  # top of bar
                weights.append(3.0)  # bar tops weighted heavily
            # Also add the bottom-left corner at lower weight
            xs.append(bx + bw / 2)
            ys.append(by)  # bottom of bar
            weights.append(0.5)  # bar bottoms barely matter
        except Exception:
            pass

    base = {
        "loc": preferred or "upper right",
        "framealpha": 0.95,
        "facecolor": "white",
        "edgecolor": "black",
        "fancybox": True,
        "shadow": False,
    }

    if not xs or not ys:
        return base

    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    w_arr = np.array(weights, dtype=float)

    valid = np.isfinite(xs_arr) & np.isfinite(ys_arr)
    xs_arr = xs_arr[valid]
    ys_arr = ys_arr[valid]
    w_arr = w_arr[valid]

    if len(xs_arr) == 0:
        return base

    xn = (xs_arr - xlim[0]) / x_range
    yn = (ys_arr - ylim[0]) / y_range

    best_loc = preferred or "upper right"
    best_density = float("inf")

    for loc, (x0, x1, y0, y1) in _LOC_QUADRANT.items():
        mask = (xn >= x0) & (xn <= x1) & (yn >= y0) & (yn <= y1)
        density = float((w_arr[mask]).sum())
        if density < best_density:
            best_density = density
            best_loc = loc

    base["loc"] = best_loc
    return base


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
