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
        "flow_weights": {"edge_rarity": 0.4, "is_unusual_dst_port": 0.3, "protocol_rarity": 0.3},
        "auth_weight_multiplier": 1.5,
        "threshold_mode": "auto_optimize",
        "threshold_percentile": 99,
        "threshold_search_range": [90, 95, 97, 99, 99.5, 99.9],
        "path_boost_factor": 0.1,
        "temporal_decay_rate": 0.0,
        "max_hops": 4,
        "top_k_paths": 50,
        "top_outgoing_per_node": 10,
    },
    "features": {
        "betweenness_node_limit": 5000,
        "approximate_betweenness": True,
        "betweenness_cutoff": 3,
        "temporal_burst_window_pct": 0.1,
        "max_workers": 12,
    },
    "baselines": {
        "run_lanl_baselines": True,
        "run_dapt_graph": True,
        "oneclass_svm": {"kernel": "rbf", "gamma": "scale", "nu": 0.1},
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
