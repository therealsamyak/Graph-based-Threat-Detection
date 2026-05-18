"""Variant descriptors for pipeline methods (combined, auth_only, flow_only)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class VariantDescriptor:
    """Pickle-safe descriptor for a pipeline variant."""
    name: str
    event_filter: str
    feature_whitelist: tuple[str, ...]
    output_artifact_label: str


COMBINED: Final[VariantDescriptor] = VariantDescriptor(
    name="combined",
    event_filter="both",
    feature_whitelist=(
        "is_ntlm",
        "dst_in_degree",
        "is_network_logon",
        "edge_rarity",
        "src_out_degree",
    ),
    output_artifact_label="combined",
)

AUTH_ONLY: Final[VariantDescriptor] = VariantDescriptor(
    name="auth_only",
    event_filter="auth",
    feature_whitelist=(
        "is_ntlm",
        "src_out_degree",
        "edge_rarity",
    ),
    output_artifact_label="auth_only",
)

FLOW_ONLY: Final[VariantDescriptor] = VariantDescriptor(
    name="flow_only",
    event_filter="flow",
    feature_whitelist=(
        "edge_rarity",
        "is_unusual_dst_port",
        "dst_in_degree",
    ),
    output_artifact_label="flow_only",
)

_ALL_VARIANTS: Final[dict[str, VariantDescriptor]] = {
    COMBINED.name: COMBINED,
    AUTH_ONLY.name: AUTH_ONLY,
    FLOW_ONLY.name: FLOW_ONLY,
}


def get_variant(name: str) -> VariantDescriptor:
    """Get variant descriptor by name."""
    if name not in _ALL_VARIANTS:
        available = sorted(_ALL_VARIANTS.keys())
        raise ValueError(
            f"Unknown variant '{name}'. Available variants: {available}"
        )
    return _ALL_VARIANTS[name]


def list_variants() -> tuple[str, ...]:
    return tuple(sorted(_ALL_VARIANTS.keys()))


def get_all_descriptors() -> tuple[VariantDescriptor, ...]:
    return tuple(_ALL_VARIANTS[name] for name in sorted(_ALL_VARIANTS.keys()))


def validate_features_in_edge_features(
    descriptor: VariantDescriptor,
    available_features: set[str],
) -> tuple[bool, list[str]]:
    missing = [
        feat for feat in descriptor.feature_whitelist
        if feat not in available_features
    ]
    return (len(missing) == 0, missing)
