"""Variant configuration contract for pipeline methods.

Defines pickle-safe descriptors for method variants (combined, auth_only, flow_only).
Each descriptor specifies event filters, feature whitelists, and output labels.

All descriptors are frozen dataclasses with primitive fields for pickle safety.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class VariantDescriptor:
    """Pickle-safe descriptor for a pipeline method variant.

    Attributes:
        name: Unique identifier for the variant (e.g., "combined", "auth_only").
        event_filter: Event type filter for graph construction.
            - "both": Include auth and flow events
            - "auth": Include auth events only
            - "flow": Include flow events only
        feature_whitelist: Tuple of feature names to use for scoring.
            Must be internal feature names used by the pipeline.
        output_artifact_label: Label used for output directories and artifacts.
            Should match the variant name for consistency.

    Notes:
        - All fields are primitive types (str, tuple) for pickle safety.
        - Frozen dataclass ensures immutability for cross-process usage.
        - Feature names must exist in emitted edge features.
        - Auth whitelist maps to high-performing features: is_ntlm, is_network_logon, is_success_auth.
        - Flow whitelist uses internal names: source_fan_out, dst_in_degree, dst_fan_out_ratio.
        - Note: Audit name 'src_fan_out_ratio' maps internally to 'source_fan_out'.
    """
    name: str
    event_filter: str
    feature_whitelist: tuple[str, ...]
    output_artifact_label: str


# ── Variant Descriptors ────────────────────────────────────────────────────────────────

#: Combined variant: uses auth + flow events with all features.
#:
#: Preserves current combined pipeline behavior from src/scoring/edges.py.
#: Features: is_ntlm, source_fan_out, dst_in_degree, is_network_logon, dst_fan_out_ratio.
COMBINED: Final[VariantDescriptor] = VariantDescriptor(
    name="combined",
    event_filter="both",
    feature_whitelist=(
        "is_ntlm",
        "source_fan_out",
        "dst_in_degree",
        "is_network_logon",
        "dst_fan_out_ratio",
    ),
    output_artifact_label="combined",
)


#: Auth-only variant: uses auth events only with auth-specific features.
#:
#: Features: is_ntlm, is_network_logon, is_success_auth.
#: Based on top-3 auth features from task-1 feature audit.
AUTH_ONLY: Final[VariantDescriptor] = VariantDescriptor(
    name="auth_only",
    event_filter="auth",
    feature_whitelist=(
        "is_ntlm",
        "is_network_logon",
        "is_success_auth",
    ),
    output_artifact_label="auth_only",
)


#: Flow-only variant: uses flow events only with flow-specific features.
#:
#: Features: source_fan_out, dst_in_degree, dst_fan_out_ratio.
#: Based on top-3 flow features from task-1 feature audit.
#: Note: Audit name 'src_fan_out_ratio' maps internally to 'source_fan_out'.
FLOW_ONLY: Final[VariantDescriptor] = VariantDescriptor(
    name="flow_only",
    event_filter="flow",
    feature_whitelist=(
        "source_fan_out",
        "dst_in_degree",
        "dst_fan_out_ratio",
    ),
    output_artifact_label="flow_only",
)


# ── Variant Registry ────────────────────────────────────────────────────────────────────

#: All available variant descriptors in stable order.
#: Use get_variant() for safe access with validation.
_ALL_VARIANTS: Final[dict[str, VariantDescriptor]] = {
    COMBINED.name: COMBINED,
    AUTH_ONLY.name: AUTH_ONLY,
    FLOW_ONLY.name: FLOW_ONLY,
}


# ── Public API ────────────────────────────────────────────────────────────────────────

def get_variant(name: str) -> VariantDescriptor:
    """Get variant descriptor by name with validation.

    Args:
        name: Variant name (e.g., "combined", "auth_only", "flow_only").

    Returns:
        VariantDescriptor for the requested variant.

    Raises:
        ValueError: If variant name is unknown.

    Examples:
        >>> variant = get_variant("auth_only")
        >>> variant.event_filter
        'auth'
        >>> variant.feature_whitelist
        ('is_ntlm', 'is_network_logon', 'is_success_auth')
    """
    if name not in _ALL_VARIANTS:
        available = sorted(_ALL_VARIANTS.keys())
        raise ValueError(
            f"Unknown variant '{name}'. Available variants: {available}"
        )
    return _ALL_VARIANTS[name]


def list_variants() -> tuple[str, ...]:
    """List all available variant names in stable order.

    Returns:
        Tuple of variant names (e.g., ("auth_only", "combined", "flow_only")).

    Examples:
        >>> list_variants()
        ('auth_only', 'combined', 'flow_only')
    """
    return tuple(sorted(_ALL_VARIANTS.keys()))


def get_all_descriptors() -> tuple[VariantDescriptor, ...]:
    """Get all variant descriptors in stable order.

    Returns:
        Tuple of VariantDescriptor objects.

    Examples:
        >>> descriptors = get_all_descriptors()
        >>> for desc in descriptors:
        ...     print(f"{desc.name}: {desc.event_filter}")
        auth_only: auth
        combined: both
        flow_only: flow
    """
    return tuple(_ALL_VARIANTS[name] for name in sorted(_ALL_VARIANTS.keys()))


# ── Validation Helper ────────────────────────────────────────────────────────────────────

def validate_features_in_edge_features(
    descriptor: VariantDescriptor,
    available_features: set[str],
) -> tuple[bool, list[str]]:
    """Validate that all whitelisted features exist in available edge features.

    Args:
        descriptor: Variant descriptor to validate.
        available_features: Set of available feature names.

    Returns:
        Tuple of (is_valid, missing_features).
        - is_valid: True if all features are available, False otherwise.
        - missing_features: List of missing feature names (empty if valid).

    Examples:
        >>> descriptor = get_variant("auth_only")
        >>> available = {"is_ntlm", "is_network_logon", "dst_in_degree"}
        >>> validate_features_in_edge_features(descriptor, available)
        (False, ['is_success_auth'])
    """
    missing = [
        feat for feat in descriptor.feature_whitelist
        if feat not in available_features
    ]
    return (len(missing) == 0, missing)


# ── Module Export Summary ──────────────────────────────────────────────────────────────
#
# This module exports:
# - VariantDescriptor: Dataclass for variant descriptors
# - COMBINED, AUTH_ONLY, FLOW_ONLY: Pre-defined variant descriptors
# - get_variant(name): Safe descriptor lookup with validation
# - list_variants(): List all variant names
# - get_all_descriptors(): Get all descriptors
# - validate_features_in_edge_features(): Validate feature whitelist
#
# All descriptors are pickle-safe (frozen dataclass with primitive fields).
# Use get_variant() for safe access; avoid direct _ALL_VARIANTS access.