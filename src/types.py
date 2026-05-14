"""Frozen dataclasses for pipeline configuration, experiment results, and detection params."""

from __future__ import annotations

import copy
from dataclasses import dataclass, field, replace


# ── Config dataclasses ──────────────────────────────────────────────


@dataclass(frozen=True)
class DataConfig:
    lanl_dir: str = "data/LANL-Dataset-2015"
    window_size: int = 3600

    @classmethod
    def from_dict(cls, d: dict) -> DataConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class GraphConfig:
    progress_every: int = 500000

    @classmethod
    def from_dict(cls, d: dict) -> GraphConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class ScoringWeights:
    is_ntlm: float = 0.4
    is_network_logon: float = 0.3
    edge_rarity: float = 0.3

    @classmethod
    def from_dict(cls, d: dict) -> ScoringWeights:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class ScoringConfig:
    weights: ScoringWeights = field(default_factory=ScoringWeights)
    threshold_mode: str = "auto_optimize"
    threshold_percentile: float = 99
    threshold_search_range: list[float] = field(
        default_factory=lambda: [90, 95, 97, 99, 99.5, 99.9]
    )
    path_boost_factor: float = 0.1
    temporal_decay_rate: float = 0.0
    max_hops: int = 4
    top_k_paths: int = 50
    top_outgoing_per_node: int = 10

    @classmethod
    def from_dict(cls, d: dict) -> ScoringConfig:
        kwargs = {}
        for k, v in d.items():
            if k == "weights":
                kwargs[k] = ScoringWeights.from_dict(v)
            elif k == "threshold_search_range":
                kwargs[k] = list(v)
            elif k in cls.__dataclass_fields__:
                kwargs[k] = v
        return cls(**kwargs)

    def to_dict(self) -> dict:
        d: dict = {}
        for f in self.__dataclass_fields__:
            val = getattr(self, f)
            if isinstance(val, ScoringWeights):
                d[f] = val.to_dict()
            else:
                d[f] = copy.deepcopy(val)
        return d


@dataclass(frozen=True)
class FeaturesConfig:
    betweenness_node_limit: int = 5000
    approximate_betweenness: bool = True
    betweenness_cutoff: int = 3
    temporal_burst_window_pct: float = 0.1
    max_workers: int = 12

    @classmethod
    def from_dict(cls, d: dict) -> FeaturesConfig:
        return cls(**{k: v for k, v in d.items() if k in cls.__dataclass_fields__})

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in self.__dataclass_fields__.values()}


@dataclass(frozen=True)
class PipelineConfig:
    data: DataConfig = field(default_factory=DataConfig)
    graph: GraphConfig = field(default_factory=GraphConfig)
    scoring: ScoringConfig = field(default_factory=ScoringConfig)
    features: FeaturesConfig = field(default_factory=FeaturesConfig)

    @classmethod
    def from_dict(cls, d: dict) -> PipelineConfig:
        kwargs = {}
        for k, v in d.items():
            if k == "data":
                kwargs[k] = DataConfig.from_dict(v)
            elif k == "graph":
                kwargs[k] = GraphConfig.from_dict(v)
            elif k == "scoring":
                kwargs[k] = ScoringConfig.from_dict(v)
            elif k == "features":
                kwargs[k] = FeaturesConfig.from_dict(v)
            elif k in cls.__dataclass_fields__:
                kwargs[k] = v
        return cls(**kwargs)

    def to_dict(self) -> dict:
        d: dict = {}
        for f in self.__dataclass_fields__:
            val = getattr(self, f)
            if hasattr(val, "to_dict"):
                d[f] = val.to_dict()
            else:
                d[f] = copy.deepcopy(val)
        return d

    @classmethod
    def default(cls) -> PipelineConfig:
        return cls()

    def with_overrides(self, **kwargs) -> PipelineConfig:
        """Return a new PipelineConfig with nested overrides applied.

        Supports nested dict overrides like data={"lanl_dir": "/new"}.
        """
        updates: dict = {}
        for k, v in kwargs.items():
            section = getattr(self, k, None)
            if isinstance(v, dict) and hasattr(section, "from_dict"):
                updates[k] = section.__class__.from_dict(
                    {**section.to_dict(), **v}
                )
            elif k in self.__dataclass_fields__:
                updates[k] = v
        return replace(self, **updates)


# ── Experiment result ───────────────────────────────────────────────


@dataclass(frozen=True)
class ExperimentResult:
    combined_graph: object = None
    combined_edge_scores: object = None
    combined_paths: object = None
    combined_threshold: float = 0.0
    combined_edge_features: object = None
    red_pairs: frozenset = field(default_factory=frozenset)
    redteam_times: object = None
    method_results: tuple = field(default_factory=tuple)


# ── Optimized weights ───────────────────────────────────────────────────


@dataclass(frozen=True)
class OptimizedWeights:
    is_ntlm: float = 0.2
    source_fan_out: float = 0.2
    dst_in_degree: float = 0.2
    is_network_logon: float = 0.2
    dst_fan_out_ratio: float = 0.2


# ── Detection params ────────────────────────────────────────────────


@dataclass(frozen=True)
class DetectionParams:
    edge_scores: object = None
    mask_valid: object = None
    edge_pair_names: tuple = field(default_factory=tuple)
    positive_pairs_in_graph: frozenset = field(default_factory=frozenset)
    all_positive_pairs: frozenset = field(default_factory=frozenset)
    all_graph_edges: frozenset = field(default_factory=frozenset)
