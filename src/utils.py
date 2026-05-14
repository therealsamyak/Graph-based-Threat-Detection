"""Shared utilities replacing duplicated code across the codebase."""

from __future__ import annotations

import igraph as ig


def compute_edge_pair_names(g: ig.Graph) -> list[tuple[str, str]]:
    """Extract (source_name, target_name) pairs for all edges in the graph."""
    return [
        (g.vs[e.source]["name"], g.vs[e.target]["name"])
        for e in g.es
    ]


