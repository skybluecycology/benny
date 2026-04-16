"""
Schema Adapter - Runtime schema introspection layer for the Semantic Correlator.

Solves Pain Point A (Schema Drift): The correlation engine no longer assumes a fixed
label/property schema. Instead, it inspects the live Neo4j graph and generates
correct Cypher match patterns dynamically.
"""

import logging
from typing import List, Dict, Any, Optional, Tuple

logger = logging.getLogger(__name__)

# Expected entity types that the correlation engine works with
EXPECTED_ENTITY_TYPES = ["File", "Class", "Interface", "Function", "Variable", "Folder", "Documentation"]


class SchemaAdapter:
    """
    Adapts correlation queries to the actual Neo4j schema at runtime.

    The graph can store code entities in two ways:
      1. Label-based: Separate labels (`:File`, `:Class`, `:Function`) as primary labels.
      2. Property-based: Single `:CodeEntity` label with a `type` property ('File', 'Class', etc.).
      3. Hybrid: Both `:CodeEntity` base label AND a `type` property.

    This adapter inspects the graph once per session and generates correct
    Cypher MATCH clauses for whichever strategy is in use.
    """

    def __init__(self):
        self._cache: Dict[str, dict] = {}  # workspace -> introspection result
        self._strategy_cache: Dict[str, str] = {}  # workspace -> detected strategy

    def _get_introspection(self, workspace: str) -> dict:
        """Get cached introspection result or fetch fresh."""
        if workspace not in self._cache:
            from ..core.graph_db import introspect_schema
            self._cache[workspace] = introspect_schema(workspace)
            logger.info(f"SchemaAdapter: Introspected workspace '{workspace}' - "
                       f"Labels: {self._cache[workspace]['labels']}, "
                       f"RelTypes: {self._cache[workspace]['relationship_types']}")
        return self._cache[workspace]

    def invalidate(self, workspace: str = None):
        """Invalidate cache for a workspace or all workspaces."""
        if workspace:
            self._cache.pop(workspace, None)
            self._strategy_cache.pop(workspace, None)
        else:
            self._cache.clear()
            self._strategy_cache.clear()

    def detect_strategy(self, workspace: str) -> str:
        """
        Detect whether the graph uses label-based, property-based, or hybrid indexing.

        Returns: 'label-based', 'property-based', or 'hybrid'
        """
        if workspace in self._strategy_cache:
            return self._strategy_cache[workspace]

        info = self._get_introspection(workspace)
        labels = set(info.get("labels", []))
        distribution = info.get("entity_type_distribution", {})

        has_code_entity_label = "CodeEntity" in labels
        has_specific_labels = bool(labels.intersection({"File", "Class", "Function", "Interface"}))

        # Check if CodeEntity nodes have type properties
        has_type_properties = any(
            ":CodeEntity" in key and val is not None
            for key, val in distribution.items()
            if "None" not in str(val)
        )

        if has_code_entity_label and has_type_properties:
            strategy = "property-based"
        elif has_specific_labels and not has_code_entity_label:
            strategy = "label-based"
        elif has_code_entity_label and has_specific_labels:
            strategy = "hybrid"
        else:
            # Default: assume property-based (matches current codebase)
            strategy = "property-based"

        self._strategy_cache[workspace] = strategy
        logger.info(f"SchemaAdapter: Detected strategy '{strategy}' for workspace '{workspace}'")
        return strategy

    def get_valid_entity_types(self, workspace: str) -> List[str]:
        """
        Return only entity types that actually exist in the graph for this workspace.
        """
        info = self._get_introspection(workspace)
        distribution = info.get("entity_type_distribution", {})

        found_types = set()
        for key in distribution.keys():
            # key format is "['CodeEntity']:File" or "['File']:None" etc.
            parts = key.split(":")
            if len(parts) >= 2:
                type_val = parts[-1].strip()
                if type_val and type_val != "None":
                    found_types.add(type_val)

        # Also check for label-based types
        labels = set(info.get("labels", []))
        for expected in EXPECTED_ENTITY_TYPES:
            if expected in labels:
                found_types.add(expected)

        valid = [t for t in EXPECTED_ENTITY_TYPES if t in found_types]
        logger.info(f"SchemaAdapter: Valid entity types for '{workspace}': {valid}")
        return valid

    def resolve_node_match(self, entity_type: str, workspace: str, node_alias: str = "s") -> str:
        """
        Generate the correct Cypher MATCH clause for a given entity type.

        Args:
            entity_type: The type to match (e.g., 'File', 'Class')
            workspace: The workspace scope
            node_alias: The Cypher variable name (default 's')

        Returns:
            A Cypher MATCH clause string, e.g.:
            - Property-based: "MATCH (s:CodeEntity {workspace: $workspace}) WHERE s.type = 'File'"
            - Label-based: "MATCH (s:File {workspace: $workspace})"
            - Hybrid: "MATCH (s:CodeEntity {workspace: $workspace}) WHERE s.type = 'File'"
        """
        strategy = self.detect_strategy(workspace)

        if strategy == "label-based":
            return f"MATCH ({node_alias}:{entity_type} {{workspace: $workspace}})"
        else:
            # property-based or hybrid — use CodeEntity with type filter
            return f"MATCH ({node_alias}:CodeEntity {{workspace: $workspace}}) WHERE {node_alias}.type = '{entity_type}'"

    def resolve_bulk_symbol_match(self, workspace: str, node_alias: str = "s") -> Tuple[str, List[str]]:
        """
        Generate a Cypher MATCH clause that finds ALL code symbols in the workspace,
        regardless of schema strategy. Also returns the list of valid types found.

        Returns:
            Tuple of (cypher_match_clause, valid_types_list)
        """
        strategy = self.detect_strategy(workspace)
        valid_types = self.get_valid_entity_types(workspace)

        # Filter to only code-relevant types (not Folder, Documentation)
        code_types = [t for t in valid_types if t in ["File", "Class", "Interface", "Function", "Variable"]]

        if not code_types:
            logger.warning(f"SchemaAdapter: No code entity types found in workspace '{workspace}'")
            # Fallback: try matching CodeEntity without type filter
            return f"MATCH ({node_alias}:CodeEntity {{workspace: $workspace}})", []

        if strategy == "label-based":
            # Use OR across labels
            label_clauses = " OR ".join([f"{node_alias}:{t}" for t in code_types])
            return f"MATCH ({node_alias} {{workspace: $workspace}}) WHERE ({label_clauses})", code_types
        else:
            types_str = str(code_types)
            return f"MATCH ({node_alias}:CodeEntity {{workspace: $workspace}}) WHERE {node_alias}.type IN {code_types}", code_types

    def get_schema_health(self, workspace: str) -> dict:
        """
        Return a health check of the schema for this workspace.
        """
        info = self._get_introspection(workspace)
        labels = set(info.get("labels", []))
        rel_types = set(info.get("relationship_types", []))
        strategy = self.detect_strategy(workspace)
        valid_types = self.get_valid_entity_types(workspace)

        expected_labels = {"CodeEntity", "File", "Class", "Function", "Concept", "Documentation"}
        expected_rels = {"CORRELATES_WITH", "REPRESENTS", "DEFINES", "DEPENDS_ON", "INHERITS", "REL", "CODE_REL"}

        return {
            "labels": sorted(labels),
            "relationship_types": sorted(rel_types),
            "expected_labels": sorted(expected_labels),
            "missing_labels": sorted(expected_labels - labels),
            "expected_relationship_types": sorted(expected_rels),
            "missing_relationship_types": sorted(expected_rels - rel_types),
            "entity_type_distribution": info.get("entity_type_distribution", {}),
            "detected_strategy": strategy,
            "valid_entity_types": valid_types,
            "recommendation": strategy
        }


# Module-level singleton for session reuse
_adapter_instance: Optional[SchemaAdapter] = None


def get_schema_adapter() -> SchemaAdapter:
    """Get or create the module-level SchemaAdapter singleton."""
    global _adapter_instance
    if _adapter_instance is None:
        _adapter_instance = SchemaAdapter()
    return _adapter_instance
