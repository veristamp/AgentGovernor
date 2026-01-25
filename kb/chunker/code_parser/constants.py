# chunker/code_parser/constants.py
"""
Constants, mappings, and type definitions for the code parser.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

# Extension mapping now centralized in config
from config import EXTENSION_TO_TREESITTER as EXTENSION_MAP



# ATOMIC TYPES: Top-level nodes that become their own chunk
# We treat these as units. If they are too big, we split their *internal* structure.
ATOMIC_TYPES = {
    # Code
    "function_definition", "class_definition", "decorated_definition", # Python
    "function_declaration", "class_declaration", "method_definition", # JS/TS
    "function_item", "impl_item", "struct_item", # Rust
    "class_declaration", "method_declaration", "interface_declaration", # Java
    
    # Structure / Config
    "element", "script_element", "style_element", # HTML
    "rule_set", "media_statement", "keyframes_statement", # CSS
    "object", "array", # JSON
}

# Languages that strictly use { } braces (for syntax injection)
BRACE_LANGUAGES = {
    "javascript", "typescript", "tsx", "java", "go", 
    "cpp", "c", "c_sharp", "rust", "php", "css", "scss"
}

# =============================================================================
# SYMBOL EXTRACTION INFRASTRUCTURE
# =============================================================================
# These structures enable "Rich Metadata" harvesting during AST traversal.
# The Chunker extracts symbols ONCE using tree-sitter; the Harvester trusts this.

@dataclass
class Symbol:
    """A code symbol extracted from the AST."""
    name: str
    kind: str  # function, class, method, interface, struct, etc.
    start_line: int
    end_line: int
    parent: Optional[str] = None  # For nested symbols (methods inside classes)
    scope: str = "global"  # global, class, local

# Node types that DEFINE symbols (we want to extract their names)
# Maps: tree-sitter node type -> symbol kind
SYMBOL_NODE_TYPES = {
    # Python
    "function_definition": "function",
    "class_definition": "class",
    "decorated_definition": "decorated",  # Will unwrap to get inner type
    
    # JavaScript/TypeScript
    "function_declaration": "function",
    "class_declaration": "class",
    "method_definition": "method",
    "arrow_function": "arrow_function",
    "interface_declaration": "interface",
    "type_alias_declaration": "type",
    
    # Go
    "function_declaration": "function",
    "method_declaration": "method",
    "type_declaration": "type",
    
    # Rust
    "function_item": "function",
    "struct_item": "struct",
    "impl_item": "impl",
    "trait_item": "trait",
    "enum_item": "enum",
    
    # Java
    "class_declaration": "class",
    "method_declaration": "method",
    "interface_declaration": "interface",
    
    # C/C++
    "function_definition": "function",
    "struct_specifier": "struct",
    "class_specifier": "class",
}

# Node types that contain COMMENTS or DOCSTRINGS (for GLiNER semantic extraction)
COMMENT_NODE_TYPES = {
    # Python
    "comment",
    "expression_statement",  # For standalone docstrings (string expressions)
    
    # JavaScript/TypeScript
    "comment",
    
    # General
    "line_comment",
    "block_comment", 
    "documentation_comment",
}

# Node types that represent REFERENCES to other symbols
REFERENCE_NODE_TYPES = {
    "identifier",
    "call_expression",
    "attribute",  # Python: obj.method
    "member_expression",  # JS: obj.method
    "import_statement",
    "import_from_statement",
}
