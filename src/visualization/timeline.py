"""Detection timeline plotting."""

from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from src.visualization.style import (
    _apply_style,
    _save_fig,
    BG_COLOR,
    TITLE_FS,
    LABEL_FS,
    _HAS_DATEFORMATTER,
    _DateFormatter,
)


def plot_detection_timeline(
    event_times: pd.Series,
    scores: pd.Series,
    threshold: float,
    output_path: str,
    redteam_edge_indices: set[int] | None = None,
    title: str = "Detection Timeline",
) -> None:
    """Scatter timeline of anomaly scores over time with red team markers.

    Handles Unix timestamps, datetime, or sequential indices.
    Subsamples non-red-team points when > 10000 for performance.
    """
    _apply_style()
    fig, ax = plt.subplots(figsize=(12, 5), facecolor=BG_COLOR)

    times = event_times.copy()
    use_datetime = False

    if times.dtype in (np.float64, np.int64, np.float32, np.int32):
        numeric_times = pd.to_numeric(times, errors="coerce").dropna()
        if len(numeric_times) > 0 and numeric_times.max() > 1e9:
            times_dt = pd.to_datetime(numeric_times, unit="s")
            times = pd.Series(times_dt, index=numeric_times.index)
            use_datetime = True
        elif numeric_times.nunique() <= 1:
            times = pd.Series(range(len(scores)), index=scores.index)
    elif pd.api.types.is_datetime64_any_dtype(times):
        use_datetime = True

    if redteam_edge_indices is not None:
        mask_rt = pd.Series(False, index=scores.index)
        valid_idx = [i for i in redteam_edge_indices if i in scores.index]
        if valid_idx:
            mask_rt.loc[valid_idx] = True
    else:
        mask_rt = pd.Series(False, index=scores.index)

    n_total = len(scores)
    n_rt = mask_rt.sum()
    if n_total > 10000 and (n_total - n_rt) > 5000:
        non_rt_idx = scores.index[~mask_rt]
        sampled = np.random.choice(non_rt_idx, size=5000, replace=False)
        plot_idx = list(sampled) + list(scores.index[mask_rt])
        plot_idx = sorted(set(plot_idx))
    else:
        plot_idx = scores.index.tolist()

    ax.scatter(
        times.loc[plot_idx], scores.loc[plot_idx],
        s=4, alpha=0.3, color="#3498db", label="Events", rasterized=True, zorder=2,
    )

    if mask_rt.any():
        rt_loc = scores.index[mask_rt]
        ax.scatter(
            times.loc[rt_loc], scores.loc[rt_loc],
            s=20, alpha=0.8, color="#e74c3c", marker="x", linewidths=1.2,
            label="Red team", zorder=4,
        )

    ax.axhline(
        y=threshold, color="#f39c12", lw=1.5, ls="--",
        label=f"Threshold ({threshold:.2f})",
    )

    y_lo = min(0, scores.min() - 0.05)
    y_hi = scores.max() * 1.1
    ax.set_ylim(y_lo, y_hi)

    if use_datetime and _HAS_DATEFORMATTER:
        ax.xaxis.set_major_formatter(_DateFormatter("%H:%M"))
        fig.autofmt_xdate()
        x_label = "Time"
    elif "index" not in str(times.iloc[0]) if len(times) > 0 else True:
        x_label = "Event Index"
    else:
        x_label = "Time"

    ax.set_title(title, fontsize=TITLE_FS, fontweight="bold", pad=12)
    ax.set_xlabel(x_label, fontsize=LABEL_FS)
    ax.set_ylabel("Anomaly Score", fontsize=LABEL_FS)
    ax.legend(fontsize=9, framealpha=0.9, loc="upper right")
    ax.tick_params(labelsize=9)
    fig.tight_layout()
    _save_fig(fig, output_path)
