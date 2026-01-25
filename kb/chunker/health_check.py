"""
Dependency health checker and fallback manager.

Validates that all critical dependencies are working correctly
and provides graceful degradation when components fail.

Usage:
    from chunker.health_check import HealthChecker
    
    health = HealthChecker()
    report = health.check_all()
    
    if not report['tree_sitter']['available']:
        # Code parsing will use fallback (line-based splitting)
        pass
"""

from typing import Dict, Any
from config import get_logger

logger = get_logger("chunker.health_check")


class HealthChecker:
    """
    Validates chunker dependencies and reports degraded capabilities.
    """
    
    def __init__(self):
        self.results = {}
    
    def check_tokenizer(self) -> Dict[str, Any]:
        """Check if transformers tokenizer works"""
        try:
            from transformers import AutoTokenizer
            tokenizer = AutoTokenizer.from_pretrained("bert-base-uncased")
            test = tokenizer.encode("test")
            return {
                "available": True,
                "version": "ok",
                "fallback": None
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "fallback": "character-based estimation (len(text)//4)"
            }
    
    def check_tree_sitter(self) -> Dict[str, Any]:
        """Check if tree-sitter works for code parsing"""
        try:
            import tree_sitter_python
            from tree_sitter import Language, Parser
            
            PY_LANGUAGE = Language(tree_sitter_python.language())
            parser = Parser(PY_LANGUAGE)
            tree = parser.parse(b"def foo(): pass")
            
            return {
                "available": True,
                "languages": ["python", "javascript", "typescript"],  # Based on your EXTENSION_MAP
                "fallback": None
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "fallback": "line-based code splitting (no AST awareness)"
            }
    
    def check_pysbd(self) -> Dict[str, Any]:
        """Check if pysbd sentence splitter works"""
        try:
            import pysbd
            seg = pysbd.Segmenter(language="en", clean=False)
            sentences = seg.segment("Hello world. This is a test.")
            
            return {
                "available": True,
                "version": "ok",
                "fallback": None
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "fallback": "regex SENTENCE_SPLIT_RE (less accurate)"
            }
    
    def check_markdown_it(self) -> Dict[str, Any]:
        """Check if markdown-it-py works"""
        try:
            from markdown_it import MarkdownIt
            md = MarkdownIt()
            tokens = md.parse("# Test\n\nContent")
            
            return {
                "available": True,
                "version": "ok",
                "fallback": None
            }
        except Exception as e:
            return {
                "available": False,
                "error": str(e),
                "fallback": "paragraph-based splitting (no heading awareness)"
            }
    
    def check_all(self) -> Dict[str, Dict[str, Any]]:
        """Run all health checks"""
        return {
            "tokenizer": self.check_tokenizer(),
            "tree_sitter": self.check_tree_sitter(),
            "pysbd": self.check_pysbd(),
            "markdown_it": self.check_markdown_it(),
        }
    
    def print_report(self):
        """Print human-readable health report"""
        results = self.check_all()
        
        print("=" * 70)
        print("CHUNKER HEALTH CHECK")
        print("=" * 70)
        
        for component, status in results.items():
            symbol = "✅" if status['available'] else "⚠️"
            print(f"\n{symbol} {component.upper()}")
            
            if status['available']:
                print(f"   Status: Operational")
            else:
                print(f"   Status: DEGRADED")
                print(f"   Error: {status.get('error', 'Unknown')}")
                print(f"   Fallback: {status.get('fallback', 'None')}")
        
        # Summary
        total = len(results)
        working = sum(1 for s in results.values() if s['available'])
        
        print("\n" + "=" * 70)
        print(f"SUMMARY: {working}/{total} components operational")
        
        if working == total:
            print("🚀 All systems green!")
        elif working >= total * 0.75:
            print("⚠️  Operating in degraded mode (acceptable)")
        else:
            print("❌ Critical components missing - chunker may fail")
        
        return results

if __name__ == "__main__":
    checker = HealthChecker()
    checker.print_report()
