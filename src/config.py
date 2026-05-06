"""Pipeline configuration loader."""

from __future__ import annotations

import json
from pathlib import Path

from src.types import PipelineConfig


def load_config(path: str = "pipeline_config.json") -> PipelineConfig:
    p = Path(path)
    if p.is_file():
        with open(p) as f:
            return PipelineConfig.from_dict(json.load(f))
    return PipelineConfig.default()
