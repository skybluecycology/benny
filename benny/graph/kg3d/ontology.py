import json
import hashlib
from typing import Dict, List, Any
from pathlib import Path
from .schema import Node, Edge

FIXTURE_PATH = Path(__file__).parent.parent.parent.parent / "tests" / "fixtures" / "kg3d" / "ml_knowledge_graph_v1.json"

class Graph:
    def __init__(self, nodes: List[Node], edges: List[Edge]):
        self.nodes = nodes
        self.edges = edges

def load_default_ontology() -> Graph:
    """Loads the canonical ML ontology from the fixture."""
    if not FIXTURE_PATH.exists():
        raise FileNotFoundError(f"Ontology fixture not found at {FIXTURE_PATH}")
    
    with open(FIXTURE_PATH, "r") as f:
        data = json.load(f)
    
    nodes = [Node(**n) for n in data.get("nodes", [])]
    edges = [Edge(**e) for e in data.get("edges", [])]
    
    return Graph(nodes=nodes, edges=edges)

def content_hash(graph: Graph) -> str:
    """Returns a stable SHA-256 hash of the graph content."""
    # Canonicalize by sorting nodes and edges by ID
    nodes_data = sorted([n.model_dump(mode="json") for n in graph.nodes], key=lambda x: x["id"])
    edges_data = sorted([e.model_dump(mode="json") for e in graph.edges], key=lambda x: x["id"])
    
    combined = json.dumps({"nodes": nodes_data, "edges": edges_data}, sort_keys=True)
    return hashlib.sha256(combined.encode()).hexdigest()
