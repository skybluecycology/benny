"""
Triple Persistence - Merging knowledge triples into the Neo4j Graph.
"""

import logging
from typing import List, Dict, Any
from ..core.graph_db import get_driver
from ..core.schema import KnowledgeTriple

logger = logging.getLogger(__name__)

async def save_knowledge_triples(workspace: str, triples: List[KnowledgeTriple], source_file: str):
    """
    Persist a list of extracted triples into Neo4j.
    Merges Concepts and creates typed relationships.
    """
    driver = get_driver()
    
    # 1. Create the Source Document node if it doesn't exist
    source_query = """
    MERGE (d:Document {name: $name, workspace: $workspace})
    SET d.updated_at = timestamp()
    RETURN d
    """
    
    # 2. Add each triple
    # Note: We use MERGE for concepts to deduplicate them by name+workspace
    triple_query = """
    MATCH (d:Document {name: $source, workspace: $workspace})
    
    MERGE (s:Concept {name: $subject, workspace: $workspace})
    ON CREATE SET s.type = $subject_type, s.created_at = timestamp()
    ON MATCH SET s.type = $subject_type
    
    MERGE (o:Concept {name: $object, workspace: $workspace})
    ON CREATE SET o.type = $object_type, o.created_at = timestamp()
    ON MATCH SET o.type = $object_type
    
    MERGE (s)-[r:REL {predicate: $predicate}]->(o)
    ON CREATE SET r.confidence = $confidence, r.citation = $citation, r.workspace = $workspace, r.model_id = $model_id, r.strategy = $strategy
    ON MATCH SET r.confidence = $confidence, r.citation = $citation, r.model_id = $model_id, r.strategy = $strategy
    
    MERGE (d)-[:CONTAINS]->(s)
    MERGE (d)-[:CONTAINS]->(o)
    """

    with driver.session() as session:
        # Ensure source exists
        session.run(source_query, name=source_file, workspace=workspace)
        
        # Batch insert triples
        for t in triples:
            try:
                session.run(
                    triple_query,
                    source=source_file,
                    workspace=workspace,
                    subject=t.subject,
                    subject_type=t.subject_type,
                    predicate=t.predicate,
                    object=t.object,
                    object_type=t.object_type,
                    confidence=t.confidence,
                    citation=t.citation,
                    model_id=t.model_id,
                    strategy=t.strategy
                )
            except Exception as e:
                logger.error(f"Failed to save triple {t.subject}->{t.object}: {e}")

    logger.info(f"Successfully persisted {len(triples)} triples from {source_file} to graph.")
