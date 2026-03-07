# config/languages.py
"""
Central Language Configuration.

Single source of truth for:
- Supported programming languages
- File extension to language mapping
- Tree-sitter language identifiers
"""

from enum import Enum
from typing import Dict


class Language(Enum):
    """Supported programming languages for code chunks."""
    UNKNOWN = "unknown"
    PYTHON = "python"
    JAVASCRIPT = "javascript"
    JSX = "jsx"
    TYPESCRIPT = "typescript"
    TSX = "tsx"
    GO = "go"
    RUST = "rust"
    JAVA = "java"
    C = "c"
    CPP = "cpp"
    RUBY = "ruby"
    BASH = "bash"
    HTML = "html"
    CSS = "css"
    JSON = "json"
    YAML = "yaml"
    PHP = "php"
    C_SHARP = "c_sharp"


# Extension to Language enum mapping
EXTENSION_TO_LANGUAGE: Dict[str, Language] = {
    # Python
    "py": Language.PYTHON,
    "python": Language.PYTHON,
    
    # JavaScript/JSX (tree-sitter-javascript handles JSX)
    "js": Language.JAVASCRIPT,
    "jsx": Language.JAVASCRIPT,  # JSX parsed by javascript parser
    "javascript": Language.JAVASCRIPT,
    
    # TypeScript/TSX (tsx has its own parser)
    "ts": Language.TYPESCRIPT,
    "tsx": Language.TSX,
    "typescript": Language.TYPESCRIPT,
    
    # Go
    "go": Language.GO,
    
    # Rust
    "rs": Language.RUST,
    
    # Java
    "java": Language.JAVA,
    
    # C/C++
    "c": Language.C,
    "h": Language.C,
    "cpp": Language.CPP,
    "hpp": Language.CPP,
    "cc": Language.CPP,
    
    # Ruby
    "rb": Language.RUBY,
    
    # Shell
    "sh": Language.BASH,
    "bash": Language.BASH,
    
    # Web
    "html": Language.HTML,
    "htm": Language.HTML,
    "css": Language.CSS,
    
    # Data formats
    "json": Language.JSON,
    "yaml": Language.YAML,
    "yml": Language.YAML,
    
    # Other
    "php": Language.PHP,
    "cs": Language.C_SHARP,
}


# Extension to tree-sitter language name (for get_parser())
# Tree-sitter uses specific language identifiers
# NOTE: Some languages share parsers (e.g., jsx uses javascript)
# Build from EXTENSION_TO_LANGUAGE but apply overrides for special cases
_TREESITTER_OVERRIDES: Dict[str, str] = {
    # JSX files use the javascript parser (tree-sitter-javascript supports JSX)
    "jsx": "javascript",
    # Ensure consistency with tree-sitter-language-pack naming
    "bash": "bash",
    "sh": "bash",
}

EXTENSION_TO_TREESITTER: Dict[str, str] = {
    ext: _TREESITTER_OVERRIDES.get(ext, lang.value) 
    for ext, lang in EXTENSION_TO_LANGUAGE.items()
}


def get_language_from_extension(ext: str) -> Language:
    """Get Language enum from file extension."""
    return EXTENSION_TO_LANGUAGE.get(ext.lower(), Language.UNKNOWN)


def get_treesitter_lang(ext: str) -> str:
    """Get tree-sitter language string from file extension."""
    return EXTENSION_TO_TREESITTER.get(ext.lower(), "text")


def is_code_file(filename: str) -> bool:
    """Check if a file is a code file based on extension."""
    ext = filename.split(".")[-1].lower() if "." in filename else ""
    return get_language_from_extension(ext) != Language.UNKNOWN
