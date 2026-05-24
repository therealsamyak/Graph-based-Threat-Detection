"""Constants and type aliases for baseline testing."""

from __future__ import annotations

# Binary features that should NOT receive rank-percentile transform.
BINARY_FEATURES: frozenset[str] = frozenset({
    "is_ntlm",
    "is_network_logon",
    "is_success_auth",
    "is_self_loop",
    "is_user_edge",
    "is_unusual_dst_port",
})

# Feature whitelist per variant (mirrors src/variants.py).
VARIANT_FEATURE_WHITELISTS: dict[str, tuple[str, ...]] = {
    "combined": ("is_ntlm", "dst_in_degree", "is_network_logon", "edge_rarity", "src_out_degree"),
    "auth_only": ("is_ntlm", "src_out_degree", "edge_rarity"),
    "flow_only": ("edge_rarity", "is_unusual_dst_port", "dst_in_degree"),
}

VALID_VARIANTS: frozenset[str] = frozenset({"combined", "auth_only", "flow_only"})
