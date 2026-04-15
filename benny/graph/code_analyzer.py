import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Set
from tree_sitter import Language, Parser, QueryCursor
import tree_sitter_python as tspython
import tree_sitter_javascript as tsjavascript
import tree_sitter_typescript as ts_ts
import logging

logger = logging.getLogger(__name__)

# --- Language Setup ---
LANGUAGES = {
    ".py": Language(tspython.language()),
    ".js": Language(tsjavascript.language()),
    ".jsx": Language(tsjavascript.language()),
    ".ts": Language(ts_ts.language_typescript()),
    ".tsx": Language(ts_ts.language_tsx()),
}

# --- UML Pattern Queries ---
# These extract Classes, Functions, Inheritance, and Imports
QUERIES = {
    "python": """
        (class_definition
          name: (identifier) @class_name
          superclasses: (argument_list (identifier) @parent_name)? @parents
        ) @class

        (function_definition
          name: (identifier) @function_name
        ) @function

        (import_statement) @import
        (import_from_statement) @import
    """,
    "typescript": """
        (class_declaration
          name: (type_identifier) @class_name
          (class_heritage (_)? @parent_name)? @parents
        ) @class

        (function_declaration
          name: (identifier) @function_name
        ) @function

        (method_definition
          name: (property_identifier) @method_name
        ) @method

        (interface_declaration
          name: (type_identifier) @interface_name
        ) @interface

        (import_statement) @import
    """,
    "javascript": """
        (class_declaration
          name: (identifier) @class_name
          (class_heritage (_)? @parent_name)? @parents
        ) @class

        (function_declaration
          name: (identifier) @function_name
        ) @function

        (method_definition
          name: (property_identifier) @method_name
        ) @method

        (import_statement) @import
    """
}

class CodeNode:
    def __init__(self, id: str, name: str, type: str, file_path: str, metadata: Dict[str, Any] = None):
        self.id = id
        self.name = name
        self.type = type # File, Class, Function, Interface
        self.file_path = file_path
        self.metadata = metadata or {}

class CodeEdge:
    def __init__(self, source: str, target: str, type: str, metadata: Dict[str, Any] = None):
        self.source = source
        self.target = target
        self.type = type # DEFINES, CALLS, INHERITS, DEPENDS_ON
        self.metadata = metadata or {}

class CodeGraphAnalyzer:
    def __init__(self, workspace_root: str):
        self.workspace_root = Path(workspace_root)
        self.nodes: Dict[str, CodeNode] = {}
        self.edges: List[CodeEdge] = []
        self.parsers: Dict[str, Parser] = {}
        
        # Init parsers
        for ext, lang in LANGUAGES.items():
            parser = Parser(lang)
            self.parsers[ext] = parser

    def _get_node_id(self, file_path: str, name: str = None) -> str:
        rel_path = os.path.relpath(file_path, self.workspace_root)
        if name:
            return f"{rel_path}::{name}".replace("\\", "/")
        return rel_path.replace("\\", "/")

    def analyze_workspace(self, sub_dir: str = "") -> Dict[str, Any]:
        """Recursively analyze the workspace starting from sub_dir"""
        start_path = self.workspace_root / sub_dir
        if not start_path.exists():
            raise ValueError(f"Path does not exist: {start_path}")

        for root, _, files in os.walk(start_path):
            # Ignore hidden dirs and node_modules
            if any(part.startswith('.') or part == 'node_modules' or part == '__pycache__' for part in Path(root).parts):
                continue

            for file in files:
                ext = os.path.splitext(file)[1].lower()
                if ext in self.parsers:
                    self._analyze_file(os.path.join(root, file), ext)

        return {
            "nodes": [vars(n) for n in self.nodes.values()],
            "edges": [vars(e) for e in self.edges]
        }

    def _analyze_file(self, file_path: str, ext: str):
        parser = self.parsers[ext]
        rel_path = os.path.relpath(file_path, self.workspace_root).replace("\\", "/")
        
        # Create File Node
        file_node_id = self._get_node_id(file_path)
        if file_node_id not in self.nodes:
            self.nodes[file_node_id] = CodeNode(file_node_id, os.path.basename(file_path), "File", rel_path)

        with open(file_path, "rb") as f:
            content = f.read()
            tree = parser.parse(content)

        lang_key = "python" if ext == ".py" else "typescript" if ext in [".ts", ".tsx"] else "javascript"
        query_str = QUERIES.get(lang_key)
        
        if not query_str:
            return

        query = LANGUAGES[ext].query(query_str)
        cursor = QueryCursor(query)
        captures = cursor.captures(tree.root_node)
        
        # Process classes and functions
        current_class = None
        
        for tag, nodes in captures.items():
            for node in nodes:
                name = None
                node_type = None

                if tag in ["class_name", "interface_name"]:
                    name = content[node.start_byte:node.end_byte].decode("utf-8")
                    node_type = "Class" if tag == "class_name" else "Interface"
                    symbol_id = self._get_node_id(file_path, name)
                    
                    if symbol_id not in self.nodes:
                        self.nodes[symbol_id] = CodeNode(symbol_id, name, node_type, rel_path)
                        # Edge File -> Class
                        self.edges.append(CodeEdge(file_node_id, symbol_id, "DEFINES"))
                    
                    current_class = symbol_id

                elif tag in ["function_name", "method_name"]:
                    name = content[node.start_byte:node.end_byte].decode("utf-8")
                    node_type = "Function"
                    symbol_id = self._get_node_id(file_path, name)

                    if symbol_id not in self.nodes:
                        self.nodes[symbol_id] = CodeNode(symbol_id, name, node_type, rel_path)
                        # If inside a class, Class -> Method, else File -> Function
                        parent_id = current_class if current_class and tag == "method_name" else file_node_id
                        self.edges.append(CodeEdge(parent_id, symbol_id, "DEFINES"))

                elif tag == "parent_name":
                    parent_name = content[node.start_byte:node.end_byte].decode("utf-8")
                    if current_class:
                        # We don't know the exact file of the parent without full indexing
                        # but we create a virtual node for now or link and let Neo4j merge
                        target_id = f"virtual::{parent_name}"
                        self.edges.append(CodeEdge(current_class, target_id, "INHERITS"))
                        if target_id not in self.nodes:
                             self.nodes[target_id] = CodeNode(target_id, parent_name, "ExternalClass", "unknown")

                elif tag == "import":
                    # Very basic import dependency tracking
                    # A more thorough implementation would resolve these paths
                    self.edges.append(CodeEdge(file_node_id, "external_dependency", "DEPENDS_ON", {"raw": content[node.start_byte:node.end_byte].decode("utf-8")}))

    def save_to_neo4j(self, workspace: str, snapshot_id: str, name: Optional[str] = None):
        """Sync the analyzed graph to Neo4j as a unique snapshot"""
        from ..core.graph_db import write_session, create_code_scan
        
        # 1. Register the scan snapshot
        create_code_scan(snapshot_id, workspace, str(self.workspace_root), name)

        with write_session() as session:
            # 2. Add CodeEntity Nodes and link to Concepts
            for node in self.nodes.values():
                session.run("""
                    MERGE (n:CodeEntity {id: $id, workspace: $ws, snapshot_id: $snap})
                    SET n.name = $name, n.type = $type, n.file_path = $path
                    WITH n
                    MERGE (c:Concept {name: $name, workspace: $ws})
                    ON CREATE SET c.node_type = 'Concept', c.created_at = datetime()
                    MERGE (n)-[:REPRESENTS]->(c)
                """, id=node.id, ws=workspace, name=node.name, type=node.type, path=node.file_path, snap=snapshot_id)

            # 3. Add internal code relationships (DEFINES, CALLS, etc)
            for edge in self.edges:
                session.run("""
                    MATCH (s:CodeEntity {id: $src, workspace: $ws, snapshot_id: $snap})
                    MATCH (t:CodeEntity {id: $tgt, workspace: $ws, snapshot_id: $snap})
                    MERGE (s)-[r:CODE_REL {type: $rel_type}]->(t)
                    SET r.snapshot_id = $snap
                """, src=edge.source, tgt=edge.target, ws=workspace, rel_type=edge.type, snap=snapshot_id)

def get_workspace_graph(workspace_id: str, snapshot_id: Optional[str] = None):
    """Fetch the code graph from Neo4j in a format suited for Three.js"""
    from ..core.graph_db import read_session
    
    with read_session() as session:
        # If no snapshot_id provided, find the most recent one for this workspace
        if not snapshot_id:
            latest_res = session.run("""
                MATCH (s:CodeScan {workspace: $ws})
                RETURN s.scan_id AS scan_id
                ORDER BY s.created_at DESC
                LIMIT 1
            """, ws=workspace_id)
            record = latest_res.single()
            if record:
                snapshot_id = record["scan_id"]
            else:
                return {"nodes": [], "edges": []}

        result = session.run("""
            MATCH (n:CodeEntity {workspace: $ws, snapshot_id: $snap})
            OPTIONAL MATCH (n)-[r:CODE_REL {snapshot_id: $snap}]->(m:CodeEntity {workspace: $ws, snapshot_id: $snap})
            RETURN n, r, m
        """, ws=workspace_id, snap=snapshot_id)
        
        nodes = {}
        edges = []
        
        for record in result:
            n = record["n"]
            if n.element_id not in nodes:
                nodes[n.element_id] = {
                    "id": n["id"],
                    "name": n["name"],
                    "type": n["type"],
                    "path": n["file_path"],
                    "elementId": n.element_id
                }
            
            r = record["r"]
            m = record["m"]
            if r and m:
                 edges.append({
                     "source": n["id"],
                     "target": m["id"],
                     "type": r["type"]
                 })
                 
        return {"nodes": list(nodes.values()), "edges": edges}

def list_workspace_dirs(workspace_root: str) -> List[str]:
    """Helper to list directories for picker"""
    root = Path(workspace_root)
    dirs = ["/"]
    for p in root.rglob("*"):
        if p.is_dir() and not any(part.startswith('.') for part in p.parts) and "node_modules" not in p.parts:
            dirs.append(str(p.relative_to(root)).replace("\\", "/"))
    return sorted(dirs)
