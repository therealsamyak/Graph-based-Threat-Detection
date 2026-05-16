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
    """Calculate inner worker budget for nested multiprocessing pools.

    When running multiple top-level variant processes, each variant should use
    a capped number of inner workers to prevent CPU oversubscription. The default
    strategy divides CPU cores by the number of top-level variants.

    Args:
        num_top_level_variants: Number of concurrent top-level variant processes.
            Defaults to 3 (combined, auth_only, flow_only).

    Returns:
        Number of workers for inner pools (ProcessPoolExecutor). Always >= 1.
    """
    return max(1, (os.cpu_count() or 1) // num_top_level_variants)
