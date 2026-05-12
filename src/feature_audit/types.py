"""Frozen dataclasses for feature audit configuration and results."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class AuditConfig:
    holdout_frac: float = 0.5
    min_auc: float = 0.7
    log1p_features: list[str] = field(
        default_factory=lambda: [
            "src_out_degree",
            "dst_in_degree",
            "src_in_degree",
            "src_total_degree",
            "dst_out_degree",
            "dst_total_degree",
        ]
    )
    duplicate_threshold: float = 0.999
    random_seed: int = 42

    @classmethod
    def from_dict(cls, d: dict) -> AuditConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class FeatureResult:
    feature: str
    auc: float
    n_unique: int
    variance: float
    mean_redteam: float
    mean_benign: float
    delta_mean: float
    is_duplicate_of: str | None
    selected: bool

    @classmethod
    def from_dict(cls, d: dict) -> FeatureResult:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class AuditReport:
    features: list[FeatureResult]
    selected_features: list[str]
    calibration_n: int
    eval_n: int
    redteam_calibration: int
    redteam_eval: int
    config: AuditConfig
    duplicate_pairs: list[tuple[str, str]] = field(default_factory=list)
    eval_metrics: dict[str, float] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> AuditReport:
        data = dict(d)
        data["features"] = [FeatureResult.from_dict(x) for x in data.get("features", [])]
        data["config"] = AuditConfig.from_dict(data.get("config", {}))
        data["duplicate_pairs"] = [tuple(x) for x in data.get("duplicate_pairs", [])]
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {
            "features": [r.to_dict() for r in self.features],
            "selected_features": self.selected_features,
            "calibration_n": self.calibration_n,
            "eval_n": self.eval_n,
            "redteam_calibration": self.redteam_calibration,
            "redteam_eval": self.redteam_eval,
            "config": self.config.to_dict(),
            "duplicate_pairs": [list(pair) for pair in self.duplicate_pairs],
            "eval_metrics": self.eval_metrics,
        }
