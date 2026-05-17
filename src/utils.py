"""Shared utilities replacing duplicated code across the codebase."""

from __future__ import annotations

import os

import igraph as ig


def compute_edge_pair_names(g: ig.Graph) -> list[tuple[str, str]]:
    """Extract (source_name, target_name) pairs for all edges in the graph."""
    return [
        (g.vs[e.source]["name"], g.vs[e.target]["name"])
        for e in g.es
    ]


def compute_inner_worker_budget(num_top_level_variants: int = 3) -> int:
    """Divide CPU cores among top-level variant processes."""
    return max(1, (os.cpu_count() or 1) // num_top_level_variants)
