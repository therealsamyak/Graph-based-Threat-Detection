"""Figure generation package API."""

from __future__ import annotations

from src.figures.comparison import plot_metrics_summary
from src.figures.detection import plot_graph_statistics, plot_holdout_validation
from src.figures.features import plot_ablation, plot_feature_audit
from src.figures.methods import plot_method_comparison, plot_radar_chart, plot_roc_curves
from src.figures.style import apply_paper_style

__all__ = [
    "apply_paper_style",
    "plot_method_comparison",
    "plot_roc_curves",
    "plot_radar_chart",
    "plot_feature_audit",
    "plot_ablation",
    "plot_graph_statistics",
    "plot_holdout_validation",
    "plot_metrics_summary",
]
