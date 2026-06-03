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
TITLE_FS = 14
LABEL_FS = 12

NODE_COLORS = {"computer": "#3498db", "user": "#2ecc71"}
EDGE_COLORS = {"auth": "#3498db", "flow": "#e74c3c"}


def _smart_legend_loc(ax, preferred: str | None = None) -> dict:
    """Return legend kwargs placing the legend inside the least-cluttered corner.

    Analyzes data density in four quadrants to find the emptiest corner,
    then returns a dict of kwargs for ``ax.legend()``.
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
    for line in ax.get_lines():
        xdata = line.get_xdata()
        ydata = line.get_ydata()
        if len(xdata) > 0:
            xs.extend(xdata)
            ys.extend(ydata)
    for coll in ax.collections:
        offsets = coll.get_offsets()
        if len(offsets) > 0:
            xs.extend(offsets[:, 0].tolist())
            ys.extend(offsets[:, 1].tolist())
    for patch in ax.patches:
        try:
            bx = patch.get_x()
            by = patch.get_y()
            bw = patch.get_width()
            bh = patch.get_height()
            xs.extend([bx, bx + bw])
            ys.extend([by, by + bh])
        except Exception:
            pass

    if not xs or not ys:
        return {"loc": preferred or "upper right", "framealpha": 0.9}

    xs_arr = np.array(xs, dtype=float)
    ys_arr = np.array(ys, dtype=float)
    valid = np.isfinite(xs_arr) & np.isfinite(ys_arr)
    xs_arr = xs_arr[valid]
    ys_arr = ys_arr[valid]

    if len(xs_arr) == 0:
        return {"loc": preferred or "upper right", "framealpha": 0.9}

    xn = (xs_arr - xlim[0]) / x_range
    yn = (ys_arr - ylim[0]) / y_range

    best_loc = preferred or "upper right"
    best_density = float("inf")

    for loc, (x0, x1, y0, y1) in _LOC_QUADRANT.items():
        mask = (xn >= x0) & (xn <= x1) & (yn >= y0) & (yn <= y1)
        density = float(mask.sum())
        if density < best_density:
            best_density = density
            best_loc = loc

    return {"loc": best_loc, "framealpha": 0.9}


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
