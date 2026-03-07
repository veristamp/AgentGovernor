"""
Concept Harvester Configuration

Optimized for:
- Code library documentation
- Scientific research papers
- GitHub code parsing
- AI/ML research

Settings are environment-configurable for different deployment contexts.
"""

import os

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional
from config import get_logger

logger = get_logger("concept_harvester.config")

def _detect_device() -> str:
    """Detect CUDA availability lazily."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"

@dataclass
class HarvesterConfig:
    """
    Configuration for the Concept Harvester.
    
    Tuned for technical documentation and research content.
    All settings are environment-configurable via env vars.
    
    Environment Variables:
        GLINER_MODEL: Model name (default: urchade/gliner_medium-v2.1)
        BASE_THRESH: Confidence threshold 0.0-1.0 (default: 0.50)
        MAX_TEXT_CHARS: Max chars per extraction (default: 2000)
        ONTOLOGY_PATH: Path to ontology.yaml
    """
    
    # ==========================================================================
    # MODEL SETTINGS
    # ==========================================================================
    
    # GLiNER model - medium-v2.1 is a good balance of speed/quality
    # For higher accuracy, try: "urchade/gliner_large-v2.1"
    model_name: str = os.getenv("GLINER_MODEL", "urchade/gliner_medium-v2.1")
    
    # Device: auto-detect CUDA or fallback to CPU
    device: str = field(default_factory=_detect_device)
    
    # ==========================================================================
    # EXTRACTION THRESHOLDS
    # ==========================================================================
    
    # Confidence threshold for concept extraction
    # LOWER = more concepts but more noise
    # HIGHER = fewer concepts but higher precision
    # 
    # Recommended values:
    #   0.40 - Discovery mode (find everything)
    #   0.50 - Balanced (default for technical docs)
    #   0.60 - Precision mode (high-confidence only)
    base_threshold: float = float(os.getenv("BASE_THRESH", "0.50"))
    
    # ==========================================================================
    # TEXT PROCESSING
    # ==========================================================================
    
    # Maximum characters to process per extraction
    # GLiNER works best with ~2000 chars. Longer texts are truncated.
    max_text_chars: int = int(os.getenv("MAX_TEXT_CHARS", "2000"))
    
    # Batch size for concurrent concept extraction
    # Higher values use more memory but process faster
    batch_size: int = int(os.getenv("CONCEPT_BATCH_SIZE", "32"))
    
    # ==========================================================================
    # ONTOLOGY
    # ==========================================================================
    
    # Path to the ontology YAML file
    # This defines what concept types GLiNER will extract
    ontology_path: str = os.getenv(
        "ONTOLOGY_PATH", 
        str(Path(__file__).parent / "ontology.yaml")
    )
    
    # ==========================================================================
    # OUTPUT SETTINGS
    # ==========================================================================
    
    # Include confidence scores in output
    include_scores: bool = True
    
    # Glob pattern for finding chunker output files
    input_glob: str = os.getenv("INPUT_GLOB", "*_structured.json")
    
    # ==========================================================================
    # INTERNAL STATE
    # ==========================================================================
    
    # Loaded ontology labels (populated in __post_init__)
    ontology: List[str] = field(init=False)
    
    def __post_init__(self):
        """Load ontology from YAML on initialization."""
        self.ontology = self._load_ontology()
        logger.info(f"HarvesterConfig: {len(self.ontology)} labels, threshold={self.base_threshold}, device={self.device}")
    
    def _load_ontology(self) -> List[str]:
        """
        Load the label set from YAML ontology file.
        
        The YAML structure can have multiple categories, but they are
        flattened into a single set of unique labels for GLiNER.
        """
        try:
            import yaml
            if os.path.exists(self.ontology_path):
                with open(self.ontology_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                
                # Flatten all categories into unique labels
                unique_labels = set()
                for category_name, labels in data.items():
                    if isinstance(labels, list):
                        unique_labels.update(labels)
                        logger.debug(f"Loaded {len(labels)} labels from '{category_name}'")
                
                if unique_labels:
                    return sorted(unique_labels)
                    
        except Exception as e:
            logger.warning(f"Failed to load ontology from {self.ontology_path}: {e}")
            
        return self._get_fallback_ontology()
    
    def _get_fallback_ontology(self) -> List[str]:
        """
        Fallback ontology for when YAML loading fails.
        
        Covers the core technical and research concepts.
        """
        return [
            # Software
            "Technology", "Framework", "Library", "Programming Language",
            "Database", "Protocol", "Design Pattern", "Architecture", "API",
            
            # AI/ML
            "Algorithm", "Machine Learning Model", "Neural Network", 
            "Language Model", "Embedding", "Vector Database",
            
            # Research
            "Methodology", "Concept", "Theorem", "Research Paper",
            
            # Entities
            "Organization", "Product", "Service", "Open Source Project",
        ]
    
    def get_label_count(self) -> int:
        """Return the number of ontology labels."""
        return len(self.ontology)
    
    def add_labels(self, labels: List[str]) -> None:
        """
        Dynamically add labels to the ontology.
        
        Useful for corpus-specific concepts discovered during processing.
        """
        current_set = set(self.ontology)
        new_labels = [l for l in labels if l not in current_set]
        if new_labels:
            self.ontology.extend(new_labels)
            logger.info(f"Added {len(new_labels)} dynamic labels to ontology")
