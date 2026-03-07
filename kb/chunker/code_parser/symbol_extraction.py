# chunker/code_parser/symbol_extraction.py
"""
Symbol, comment, and reference extraction functions using tree-sitter AST.
These functions enable "Rich Metadata" harvesting during AST traversal.
"""
from __future__ import annotations
from typing import List, Dict, Any, Optional

from .constants import SYMBOL_NODE_TYPES, COMMENT_NODE_TYPES, REFERENCE_NODE_TYPES


def extract_symbols_from_node(
    node, 
    code_bytes: bytes, 
    parent_name: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Recursively extract symbol definitions from an AST node.
    
    Returns a list of symbol dicts suitable for chunk metadata:
    [{"name": "MyClass", "kind": "class", "start_line": 10, "end_line": 50}, ...]
    """
    symbols = []
    
    # Check if this node defines a symbol
    node_type = node.type
    
    # Unwrap decorated definitions (Python @decorator)
    target_node = node
    if node_type == "decorated_definition":
        definition = node.child_by_field_name("definition")
        if definition:
            target_node = definition
            node_type = target_node.type
    
    # Unwrap export statements (JS/TS export default/named)
    if node_type == "export_statement":
        declaration = node.child_by_field_name("declaration")
        if declaration:
            target_node = declaration
            node_type = target_node.type
    
    # Check if this is a symbol-defining node
    if node_type in SYMBOL_NODE_TYPES:
        kind = SYMBOL_NODE_TYPES[node_type]
        
        # Extract the name
        name = None
        name_node = target_node.child_by_field_name("name")
        if name_node:
            name = code_bytes[name_node.start_byte:name_node.end_byte].decode("utf8", errors="replace")
        
        if name:
            symbol = {
                "name": name,
                "kind": kind,
                "start_line": node.start_point[0],
                "end_line": node.end_point[0],
            }
            if parent_name:
                symbol["parent"] = parent_name
                symbol["scope"] = "class" if kind in ("method", "function") else "global"
            else:
                symbol["scope"] = "global"
            
            symbols.append(symbol)
            
            # Recurse into children with this as parent (for nested definitions)
            body = target_node.child_by_field_name("body") or target_node.child_by_field_name("block")
            if body:
                for child in body.children:
                    symbols.extend(extract_symbols_from_node(child, code_bytes, name))
    
    return symbols


def extract_comments_from_node(node, code_bytes: bytes) -> str:
    """
    Extract all comments and docstrings from a node subtree.
    
    Returns a single string of concatenated comment text, cleaned up for GLiNER.
    This is the "semantic" content that the Harvester will pass to GLiNER.
    """
    comments = []
    
    def _recurse(n):
        # Check for comment nodes
        if n.type in COMMENT_NODE_TYPES:
            text = code_bytes[n.start_byte:n.end_byte].decode("utf8", errors="replace")
            
            # Clean up comment syntax
            text = text.strip()
            
            # Python/Shell comments
            if text.startswith("#"):
                text = text.lstrip("#").strip()
            # C-style single line
            elif text.startswith("//"):
                text = text.lstrip("/").strip()
            # C-style block comments
            elif text.startswith("/*"):
                text = text[2:]
                if text.endswith("*/"):
                    text = text[:-2]
                text = text.strip()
            # Python docstrings (triple quotes)
            elif text.startswith('"""') or text.startswith("'''"):
                quote = text[:3]
                text = text[3:]
                if text.endswith(quote):
                    text = text[:-3]
                text = text.strip()
            
            # Filter out noise (too short, only punctuation, etc.)
            if len(text) > 5 and not text.startswith("noqa") and not text.startswith("type:"):
                comments.append(text)
        
        # Check for Python docstrings (first child of function/class body is a string)
        if n.type == "expression_statement":
            child = n.children[0] if n.children else None
            if child and child.type == "string":
                text = code_bytes[child.start_byte:child.end_byte].decode("utf8", errors="replace")
                # Remove quotes
                for quote in ['"""', "'''", '"', "'"]:
                    if text.startswith(quote) and text.endswith(quote):
                        text = text[len(quote):-len(quote)]
                        break
                text = text.strip()
                if len(text) > 10:  # Docstrings are usually longer
                    comments.append(text)
        
        # Recurse
        for child in n.children:
            _recurse(child)
    
    _recurse(node)
    
    # Join with newlines, deduplicate adjacent duplicates
    seen = set()
    unique = []
    for c in comments:
        if c not in seen:
            seen.add(c)
            unique.append(c)
    
    return "\n".join(unique)


def extract_references_from_node(node, code_bytes: bytes) -> List[Dict[str, Any]]:
    """
    Extract symbol references (function calls, imports, etc.) from a node.
    
    Returns list of referenced symbol names with line numbers:
    [{"name": "validate_password", "line": 15}, ...]
    """
    references = []
    seen = set()  # Avoid duplicates
    
    def _recurse(n):
        # Import statements
        if n.type in ("import_statement", "import_from_statement"):
            # Extract imported names
            for child in n.children:
                if child.type in ("dotted_name", "identifier"):
                    name = code_bytes[child.start_byte:child.end_byte].decode("utf8", errors="replace")
                    # Take the first part of dotted names (e.g., "os" from "os.path")
                    name = name.split(".")[0]
                    if name and name not in seen and len(name) > 1:
                        seen.add(name)
                        references.append({"name": name, "line": n.start_point[0]})
        
        # Function calls
        elif n.type == "call_expression" or n.type == "call":
            # Get the function name
            func = n.child_by_field_name("function") or (n.children[0] if n.children else None)
            if func:
                if func.type == "identifier":
                    name = code_bytes[func.start_byte:func.end_byte].decode("utf8", errors="replace")
                    if name and name not in seen and len(name) > 1:
                        seen.add(name)
                        references.append({"name": name, "line": n.start_point[0]})
                elif func.type in ("attribute", "member_expression"):
                    # Get method name from obj.method
                    attr = func.child_by_field_name("attribute") or func.child_by_field_name("property")
                    if attr:
                        name = code_bytes[attr.start_byte:attr.end_byte].decode("utf8", errors="replace")
                        if name and name not in seen and len(name) > 1:
                            seen.add(name)
                            references.append({"name": name, "line": n.start_point[0]})
        
        # Recurse
        for child in n.children:
            _recurse(child)
    
    _recurse(node)
    return references
