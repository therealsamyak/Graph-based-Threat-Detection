"""Frozen dataclasses for eval configuration and results."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class EvalConfig:
    holdout_frac: float = 0.5
    seed: int = 42
    feature_list: list[str] = field(
        default_factory=lambda: [
            "is_ntlm",
            "source_fan_out",
            "dst_in_degree",
            "is_network_logon",
            "dst_fan_out_ratio",
        ]
    )
    output_dir: Path = field(default_factory=lambda: Path("analysis_results"))

    @classmethod
    def from_dict(cls, d: dict) -> EvalConfig:
        data = dict(d)
        if "output_dir" in data:
            data["output_dir"] = Path(data["output_dir"])
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {
            f.name: str(getattr(self, f.name)) if f.name == "output_dir" else getattr(self, f.name)
            for f in self.__dataclass_fields__.values()
        }


@dataclass(frozen=True)
class HoldoutResult:
    weights: dict[str, float]
    auc_cal: float
    auc_eval: float
    gap: float

    @classmethod
    def from_dict(cls, d: dict) -> HoldoutResult:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class AblationResult:
    name: str
    columns: list[str]
    n_features: int
    cal_auc: float
    eval_auc: float

    @classmethod
    def from_dict(cls, d: dict) -> AblationResult:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class FeatureSweepResult:
    name: str
    added_columns: list[str]
    n_features: int
    cal_auc: float
    eval_auc: float
    delta_vs_base: float

    @classmethod
    def from_dict(cls, d: dict) -> FeatureSweepResult:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}