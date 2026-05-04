"""Graph-level feature extraction: density, clustering, components."""

from __future__ import annotations

import igraph as ig
import numpy as np

from src.features.node import extract_node_features
from src.features.edge import extract_edge_features


def extract_graph_features(g: ig.Graph) -> dict:
    if g.vcount() == 0:
        return {
            "density": 0.0,
            "avg_clustering": 0.0,
            "component_count": 0,
            "node_count": 0,
            "edge_count": 0,
        }
    ug = g.copy()
    ug.to_undirected()
    clustering = ug.transitivity_local_undirected(mode="zero")
    return {
        "density": g.density(),
        "avg_clustering": float(np.mean(clustering)) if clustering else 0.0,
        "component_count": len(g.connected_components(mode="weak")),
        "node_count": g.vcount(),
        "edge_count": g.ecount(),
    }


def extract_all_features(g: ig.Graph, config: dict | None = None) -> dict:
    return {
        "node_features": extract_node_features(g, config=config),
        "edge_features": extract_edge_features(g, config=config),
        "graph_features": extract_graph_features(g),
    }
