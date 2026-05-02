"""Pipeline configuration loader."""

from __future__ import annotations

import json
from pathlib import Path

_DEFAULTS: dict = {
    "data": {
        "lanl_dir": "data/LANL-Dataset-2015",
        "dapt_dir": "data/DAPT2020",
        "window_size": 3600,
    },
    "graph": {
        "progress_every": 500000,
    },
    "scoring": {
        "weights": {"is_ntlm": 0.4, "is_network_logon": 0.3, "edge_rarity": 0.3},
        "threshold_percentile": 90,
        "max_hops": 4,
        "top_k_paths": 50,
        "top_outgoing_per_node": 10,
    },
    "features": {
        "betweenness_node_limit": 5000,
        "temporal_burst_window_pct": 0.1,
        "max_workers": 12,
    },
    "baselines": {
        "oneclass_svm": {"kernel": "rbf", "gamma": "scale", "nu": 0.05},
        "isolation_forest": {"n_estimators": 100, "contamination": 0.05, "random_state": 42},
    },
}


def load_config(path: str = "pipeline_config.json") -> dict:
    """Load pipeline config from JSON file, falling back to defaults."""
    p = Path(path)
    if p.is_file():
        with open(p) as f:
            return json.load(f)
    return _DEFAULTS.copy()
