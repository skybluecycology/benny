"""
Graph Database Connection - Neo4j integration for the Synthesis Knowledge Engine.

Provides connection management and core Cypher query helpers for the
relational graph, embedding storage, and synthesis operations.
"""

import os
import json
from typing import Optional, Dict, Any, List, Tuple
from neo4j import GraphDatabase

# =============================================================================
# CONNECTION CONFIGURATION
# =============================================================================

NEO4J_URI = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.environ.get("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.environ.get("NEO4J_PASSWORD", "password")

_driver = None


def get_driver():
    """Get or create Neo4j driver singleton."""
    global _driver
    if _driver is None:
        _driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    return _driver


def close_driver():
    """Close the Neo4j driver."""
    global _driver
    if _driver:
        _driver.close()
        _driver = None


def verify_connectivity() -> dict:
    """Verify Neo4j is reachable and return server info."""
    try:
        driver = get_driver()
        driver.verify_connectivity()
        with driver.session() as session:
            result = session.run("RETURN 1 AS ping")
            record = result.single()
            return {
                "status": "connected",
                "ping": record["ping"],
                "uri": NEO4J_URI
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "uri": NEO4J_URI
        }


# =============================================================================
# SCHEMA INITIALISATION
# =============================================================================

def init_schema():
    """
    Create constraints and indexes for the knowledge graph.
    
    Node labels:
        - Concept: core idea/entity extracted from documents
        - Source: the originating document
    
    Relationship types:
        - RELATES_TO: explicit relationship with a predicate property
        - SOURCED_FROM: links a concept back to its source document
        - CONFLICTS_WITH: marks contradictory statements
        - ANALOGOUS_TO: structural isomorphism link
    """
    driver = get_driver()
    with driver.session() as session:
        # Unique constraint on Concept name within a workspace
        session.run("""
            CREATE CONSTRAINT concept_unique IF NOT EXISTS
            FOR (c:Concept) REQUIRE (c.name, c.workspace) IS UNIQUE
        """)
        # Unique constraint on Source name within a workspace
        session.run("""
            CREATE CONSTRAINT source_unique IF NOT EXISTS
            FOR (s:Source) REQUIRE (s.name, s.workspace) IS UNIQUE
        """)
        # Vector index for concept embeddings (Neo4j 5 native vector)
        try:
            session.run("""
                CREATE VECTOR INDEX concept_embedding IF NOT EXISTS
                FOR (c:Concept) ON (c.embedding)
                OPTIONS {
                    indexConfig: {
                        `vector.dimensions`: 1536,
                        `vector.similarity_function`: 'cosine'
                    }
                }
            """)
        except Exception:
            # Vector indexes may already exist or not be supported
            pass

    return {"status": "schema_initialized"}


# =============================================================================
# TRIPLE MANAGEMENT (Subject, Predicate, Object)
# =============================================================================

def add_triple(
    subject: str,
    predicate: str,
    obj: str,
    workspace: str = "default",
    source_name: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    timestamp: Optional[str] = None,
    section: Optional[str] = None,
    subject_type: str = "Concept",
    object_type: str = "Concept",
    citation: str = "",
    confidence: float = 1.0
) -> dict:
    """
    Add a knowledge triple to the graph.
    
    Creates or merges Subject and Object as Concept nodes (with types), 
    then creates a RELATES_TO edge with the predicate, citation, and confidence.
    """
    driver = get_driver()
    meta_json = json.dumps(metadata or {})
    
    with driver.session() as session:
        result = session.run("""
            MERGE (s:Concept {name: $subject, workspace: $workspace})
            ON CREATE SET s.created_at = datetime(), s.domain = '', s.node_type = $subject_type
            ON MATCH SET s.node_type = $subject_type
            MERGE (o:Concept {name: $obj, workspace: $workspace})
            ON CREATE SET o.created_at = datetime(), o.domain = '', o.node_type = $object_type
            ON MATCH SET o.node_type = $object_type
            
            CREATE (s)-[r:RELATES_TO {
                predicate: $predicate,
                source: $source_name,
                metadata: $metadata,
                section: $section,
                citation: $citation,
                confidence: $confidence,
                created_at: datetime(),
                timestamp: $timestamp
            }]->(o)
            
            RETURN elementId(s) AS sid, elementId(o) AS oid, elementId(r) AS rid
        """, subject=subject, predicate=predicate, obj=obj,
             workspace=workspace, source_name=source_name or "",
             metadata=meta_json, timestamp=timestamp or "",
             section=section or "", citation=citation, confidence=confidence,
             subject_type=subject_type, object_type=object_type)
        
        record = result.single()
        return {
            "subject_id": record["sid"],
            "object_id": record["oid"],
            "relation_id": record["rid"],
            "triple": [subject, predicate, obj]
        }


def add_source_link(concept_name: str, source_name: str, workspace: str = "default") -> dict:
    """Link a concept node to its source document."""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (c:Concept {name: $concept, workspace: $workspace})
            MERGE (s:Source {name: $source, workspace: $workspace})
            ON CREATE SET s.created_at = datetime()
            MERGE (c)-[:SOURCED_FROM]->(s)
        """, concept=concept_name, source=source_name, workspace=workspace)
    return {"status": "linked", "concept": concept_name, "source": source_name}


def add_conflict(
    concept_a: str,
    concept_b: str,
    description: str,
    workspace: str = "default"
) -> dict:
    """Mark a conflict between two concepts."""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (a:Concept {name: $a, workspace: $workspace})
            MERGE (b:Concept {name: $b, workspace: $workspace})
            CREATE (a)-[:CONFLICTS_WITH {
                description: $description,
                created_at: datetime()
            }]->(b)
        """, a=concept_a, b=concept_b, description=description, workspace=workspace)
    return {"status": "conflict_added", "between": [concept_a, concept_b]}


def add_analogy(
    concept_a: str,
    concept_b: str,
    description: str,
    pattern: str,
    workspace: str = "default"
) -> dict:
    """Create a structural isomorphism link (cross-domain analogy)."""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (a:Concept {name: $a, workspace: $workspace})
            MERGE (b:Concept {name: $b, workspace: $workspace})
            CREATE (a)-[:ANALOGOUS_TO {
                description: $description,
                pattern: $pattern,
                created_at: datetime()
            }]->(b)
        """, a=concept_a, b=concept_b, description=description,
             pattern=pattern, workspace=workspace)
    return {"status": "analogy_added", "between": [concept_a, concept_b], "pattern": pattern}


# =============================================================================
# EMBEDDING STORAGE
# =============================================================================

def set_concept_embedding(concept_name: str, embedding: List[float], workspace: str = "default") -> dict:
    """Store a vector embedding on a Concept node."""
    driver = get_driver()
    with driver.session() as session:
        session.run("""
            MERGE (c:Concept {name: $name, workspace: $workspace})
            SET c.embedding = $embedding
        """, name=concept_name, embedding=embedding, workspace=workspace)
    return {"status": "embedding_set", "concept": concept_name, "dimensions": len(embedding)}


def vector_search(query_embedding: List[float], workspace: str = "default", top_k: int = 10) -> List[dict]:
    """Find the nearest concepts by vector similarity."""
    driver = get_driver()
    with driver.session() as session:
        # Use Neo4j's native vector index
        try:
            result = session.run("""
                CALL db.index.vector.queryNodes('concept_embedding', $topK, $embedding)
                YIELD node, score
                WHERE node.workspace = $workspace
                RETURN node.name AS name, node.domain AS domain, score
                ORDER BY score DESC
            """, embedding=query_embedding, topK=top_k, workspace=workspace)
            return [dict(r) for r in result]
        except Exception:
            # Fallback: brute-force cosine (for dev / small graphs)
            result = session.run("""
                MATCH (c:Concept {workspace: $workspace})
                WHERE c.embedding IS NOT NULL
                RETURN c.name AS name, c.domain AS domain, c.embedding AS embedding
            """, workspace=workspace)
            
            from math import sqrt
            records = list(result)
            if not records:
                return []
            
            def cosine_sim(a, b):
                dot = sum(x * y for x, y in zip(a, b))
                na = sqrt(sum(x * x for x in a))
                nb = sqrt(sum(x * x for x in b))
                return dot / (na * nb) if (na and nb) else 0.0
            
            scored = []
            for rec in records:
                sim = cosine_sim(query_embedding, rec["embedding"])
                scored.append({"name": rec["name"], "domain": rec["domain"] or "", "score": sim})
            
            scored.sort(key=lambda x: x["score"], reverse=True)
            return scored[:top_k]


# =============================================================================
# GRAPH QUERYING
# =============================================================================

def get_full_graph(workspace: str = "default") -> dict:
    """
    Return the full knowledge graph for a workspace as nodes + edges
    suitable for 3d-force-graph rendering.
    """
    driver = get_driver()
    with driver.session() as session:
        # Nodes
        node_result = session.run("""
            MATCH (n {workspace: $workspace})
            WHERE n:Concept OR n:Source
            RETURN elementId(n) AS id, labels(n) AS labels, n.name AS name,
                   n.domain AS domain, n.created_at AS created_at, n.node_type AS node_type
        """, workspace=workspace)
        
        nodes = []
        for rec in node_result:
            node = {
                "id": str(rec["id"]),
                "name": rec["name"],
                "labels": rec["labels"],
                "domain": rec["domain"] or "",
                "created_at": str(rec["created_at"]) if rec["created_at"] else "",
                "node_type": rec["node_type"] or "Concept"
            }
            nodes.append(node)
        
        # Edges
        edge_result = session.run("""
            MATCH (a {workspace: $workspace})-[r]->(b {workspace: $workspace})
            RETURN elementId(a) AS source, elementId(b) AS target, type(r) AS type,
                   r.predicate AS predicate, r.description AS description,
                   r.pattern AS pattern, r.source AS source_doc,
                   r.created_at AS created_at, r.timestamp AS timestamp,
                   r.section AS section, r.citation AS citation, r.confidence AS confidence
        """, workspace=workspace)
        
        edges = []
        for rec in edge_result:
            edge = {
                "source": str(rec["source"]),
                "target": str(rec["target"]),
                "type": rec["type"],
                "predicate": rec["predicate"] or "",
                "description": rec["description"] or "",
                "pattern": rec["pattern"] or "",
                "source_doc": rec["source_doc"] or "",
                "section": rec["section"] or "",
                "citation": rec["citation"] or "",
                "confidence": rec["confidence"] if rec["confidence"] is not None else 1.0,
                "created_at": str(rec["created_at"]) if rec["created_at"] else "",
                "timestamp": rec["timestamp"] or ""
            }
            edges.append(edge)
    
    return {"nodes": nodes, "edges": edges}


def get_neighbors(concept_name: str, workspace: str = "default", depth: int = 1) -> dict:
    """Get a concept's neighbourhood (nodes + edges) up to N hops."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH path = (c:Concept {name: $name, workspace: $workspace})-[*1..""" + str(depth) + """]->(n)
            UNWIND relationships(path) AS r
            WITH DISTINCT startNode(r) AS a, r, endNode(r) AS b
            RETURN elementId(a) AS src_id, a.name AS src_name, labels(a) AS src_labels,
                   type(r) AS rel_type, r.predicate AS predicate,
                   elementId(b) AS tgt_id, b.name AS tgt_name, labels(b) AS tgt_labels
        """, name=concept_name, workspace=workspace)
        
        nodes_map = {}
        edges = []
        for rec in result:
            src_id = str(rec["src_id"])
            tgt_id = str(rec["tgt_id"])
            if src_id not in nodes_map:
                nodes_map[src_id] = {"id": src_id, "name": rec["src_name"], "labels": rec["src_labels"]}
            if tgt_id not in nodes_map:
                nodes_map[tgt_id] = {"id": tgt_id, "name": rec["tgt_name"], "labels": rec["tgt_labels"]}
            edges.append({
                "source": src_id,
                "target": tgt_id,
                "type": rec["rel_type"],
                "predicate": rec["predicate"] or ""
            })
    
    return {"nodes": list(nodes_map.values()), "edges": edges}


def get_graph_stats(workspace: str = "default") -> dict:
    """Get counts of concepts, sources, and relationships."""
    driver = get_driver()
    with driver.session() as session:
        concept_count = session.run(
            "MATCH (c:Concept {workspace: $ws}) RETURN count(c) AS n", ws=workspace
        ).single()["n"]
        
        source_count = session.run(
            "MATCH (s:Source {workspace: $ws}) RETURN count(s) AS n", ws=workspace
        ).single()["n"]
        
        rel_count = session.run(
            "MATCH (a {workspace: $ws})-[r]->(b {workspace: $ws}) RETURN count(r) AS n", ws=workspace
        ).single()["n"]
        
        conflict_count = session.run(
            "MATCH (a {workspace: $ws})-[r:CONFLICTS_WITH]->(b {workspace: $ws}) RETURN count(r) AS n", ws=workspace
        ).single()["n"]
        
        analogy_count = session.run(
            "MATCH (a {workspace: $ws})-[r:ANALOGOUS_TO]->(b {workspace: $ws}) RETURN count(r) AS n", ws=workspace
        ).single()["n"]
    
    return {
        "concepts": concept_count,
        "sources": source_count,
        "relationships": rel_count,
        "conflicts": conflict_count,
        "analogies": analogy_count
    }


def get_mapped_sources(workspace: str = "default") -> List[str]:
    """Get a list of all source documents that have been mapped into the graph."""
    driver = get_driver()
    with driver.session() as session:
        result = session.run("""
            MATCH (s:Source {workspace: $ws})
            RETURN s.name AS name
            ORDER BY s.created_at DESC
        """, ws=workspace)
        return [record["name"] for record in result]


def delete_source_from_graph(source_name: str, workspace: str = "default") -> dict:
    """
    Remove a specific document's data from the knowledge graph.
    This deletes RELATES_TO edges mapping to this source, the Source node itself,
    and any cleanups orphaned Concept nodes.
    """
    driver = get_driver()
    with driver.session() as session:
        # 1. Delete all RELATES_TO edges attributed to this source
        session.run("""
            MATCH ()-[r:RELATES_TO {source: $source_name}]->()
            DELETE r
        """, source_name=source_name)
        
        # 2. Delete the Source node and its connections (SOURCED_FROM)
        session.run("""
            MATCH (s:Source {name: $source_name, workspace: $workspace})
            DETACH DELETE s
        """, source_name=source_name, workspace=workspace)
        
        # 3. Clean up orphaned concepts and their derived relations (like Analogies or Conflicts)
        # Any concept in this workspace with no incoming or outgoing edges left is deleted.
        session.run("""
            MATCH (c:Concept {workspace: $workspace})
            WHERE NOT (c)--()
            DELETE c
        """, workspace=workspace)
        
    return {"status": "deleted", "source": source_name, "workspace": workspace}
