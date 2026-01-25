# services/chat/persona_service.py
"""
Persona Service - Business Logic for Agent Personas.

Follows the same layered pattern as other services:
- API Layer (routes/persona.py) → This Service → Config/Storage

Provides:
- Persona CRUD operations
- Persona resolution for chat requests
- Config merging with overrides
"""

from typing import Optional, Dict, Any, List
import logging

from .models import (
    PersonaDefinition,
    PersonaOverrides,
    LLMConfig,
    RAGConfig,
    MemoryConfig,
    FeedbackConfig,
)
from config import get_logger

logger = get_logger("PersonaService")


# =============================================================================
# PREDEFINED PERSONAS
# =============================================================================

DEFAULT_PERSONAS: Dict[str, PersonaDefinition] = {
    "default": PersonaDefinition(
        id="default",
        name="Default Assistant",
        description="General-purpose helpful assistant with balanced settings",
        system_prompt="You are a helpful AI assistant. Answer questions accurately and concisely.",
        tags=["general", "balanced"]
    ),
    
    "code_assistant": PersonaDefinition(
        id="code_assistant",
        name="Code Assistant",
        description="Optimized for code understanding and generation",
        system_prompt="""You are an expert software engineer assistant. 
Help users understand, write, and debug code. Be precise and provide working examples.
Always explain your reasoning when suggesting code changes.""",
        llm=LLMConfig(temperature=0.3, max_tokens=4096),
        rag=RAGConfig(retrieval_limit=10, use_rerank=True),
        memory=MemoryConfig(history_k=20),
        tags=["code", "technical", "precise"]
    ),
    
    "creative_writer": PersonaDefinition(
        id="creative_writer",
        name="Creative Writer",
        description="Optimized for creative writing and brainstorming",
        system_prompt="""You are a creative writing assistant with a flair for storytelling.
Help users write engaging content, explore ideas, and craft compelling narratives.
Be imaginative and offer multiple creative directions.""",
        llm=LLMConfig(temperature=0.9, max_tokens=4096),
        rag=RAGConfig(enabled=False),
        memory=MemoryConfig(history_k=5, include_ltm=False),
        feedback=FeedbackConfig(auto_learn=False),
        tags=["creative", "writing", "brainstorm"]
    ),
    
    "research_analyst": PersonaDefinition(
        id="research_analyst",
        name="Research Analyst",
        description="Deep research with extensive context and memory",
        system_prompt="""You are a research analyst assistant. 
Provide thorough, well-cited analysis. Cross-reference information and identify patterns.
Always cite your sources and acknowledge uncertainty.""",
        llm=LLMConfig(temperature=0.5, max_tokens=8192),
        rag=RAGConfig(retrieval_limit=15, use_rerank=True, use_mmr=True, mmr_lambda=0.5),
        memory=MemoryConfig(history_k=30, include_ltm=True, auto_compress=True),
        tags=["research", "analytical", "thorough"]
    ),
    
    "ephemeral": PersonaDefinition(
        id="ephemeral",
        name="Ephemeral Chat",
        description="Stateless mode - no history, no memory, no learning",
        system_prompt="You are a helpful assistant. This is a stateless conversation.",
        rag=RAGConfig(enabled=True),
        memory=MemoryConfig(include_history=False, history_k=0, include_ltm=False),
        feedback=FeedbackConfig(auto_learn=False, extract_citations=False),
        tags=["stateless", "ephemeral", "privacy"]
    )
}


class PersonaService:
    """
    Service layer for persona operations.
    
    Architecture:
        API (routes/persona.py)
            ↓
        PersonaService (this file) - Business logic
            ↓
        In-memory store (default) or DB (custom personas)
    """
    
    def __init__(self):
        """Initialize with default personas."""
        self._personas: Dict[str, PersonaDefinition] = DEFAULT_PERSONAS.copy()
        self._custom_personas: Dict[str, PersonaDefinition] = {}
    
    # =========================================================================
    # PERSONA RETRIEVAL
    # =========================================================================
    
    def get_persona(self, persona_id: str) -> Optional[PersonaDefinition]:
        """
        Get a persona by ID.
        
        Args:
            persona_id: Persona identifier
            
        Returns:
            PersonaDefinition or None
        """
        # Check custom first, then defaults
        return self._custom_personas.get(persona_id) or self._personas.get(persona_id)
    
    def list_personas(self, include_custom: bool = True) -> List[PersonaDefinition]:
        """
        List all available personas.
        
        Args:
            include_custom: Include user-created personas
            
        Returns:
            List of PersonaDefinitions
        """
        personas = list(self._personas.values())
        if include_custom:
            personas.extend(self._custom_personas.values())
        return personas
    
    def list_persona_ids(self) -> List[str]:
        """Get list of all persona IDs."""
        return list(self._personas.keys()) + list(self._custom_personas.keys())
    
    # =========================================================================
    # PERSONA CRUD (Custom Personas)
    # =========================================================================
    
    def create_persona(
        self,
        persona: PersonaDefinition,
        owner: Optional[str] = None
    ) -> PersonaDefinition:
        """
        Create a custom persona.
        
        Args:
            persona: Persona definition
            owner: Owner/creator ID
            
        Returns:
            Created persona
        """
        if persona.id in self._personas:
            raise ValueError(f"Cannot override default persona: {persona.id}")
        
        if owner:
            persona.owner = owner
        
        self._custom_personas[persona.id] = persona
        logger.info(f"🎭 Created persona: {persona.id}")
        return persona
    
    def update_persona(
        self,
        persona_id: str,
        updates: Dict[str, Any]
    ) -> Optional[PersonaDefinition]:
        """
        Update a custom persona.
        
        Args:
            persona_id: Persona to update
            updates: Fields to update
            
        Returns:
            Updated persona or None
        """
        if persona_id in self._personas:
            raise ValueError(f"Cannot modify default persona: {persona_id}")
        
        if persona_id not in self._custom_personas:
            return None
        
        current = self._custom_personas[persona_id]
        updated_data = current.dict()
        updated_data.update(updates)
        
        self._custom_personas[persona_id] = PersonaDefinition(**updated_data)
        logger.info(f"🎭 Updated persona: {persona_id}")
        return self._custom_personas[persona_id]
    
    def delete_persona(self, persona_id: str) -> bool:
        """
        Delete a custom persona.
        
        Args:
            persona_id: Persona to delete
            
        Returns:
            True if deleted
        """
        if persona_id in self._personas:
            raise ValueError(f"Cannot delete default persona: {persona_id}")
        
        if persona_id in self._custom_personas:
            del self._custom_personas[persona_id]
            logger.info(f"🎭 Deleted persona: {persona_id}")
            return True
        
        return False
    
    # =========================================================================
    # CONFIG RESOLUTION
    # =========================================================================
    
    def resolve_config(
        self,
        persona_id: Optional[str],
        overrides: Optional[PersonaOverrides] = None,
        request_params: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Resolve final configuration from persona + overrides.
        
        Priority: request_params > overrides > persona > defaults
        
        Args:
            persona_id: Persona to use (None = defaults)
            overrides: PersonaOverrides object
            request_params: Direct request parameters
            
        Returns:
            Merged config dict ready for ChatService
        """
        # Start with defaults
        config = {
            "temperature": 0.7,
            "max_tokens": 1024,
            "use_rag": True,
            "retrieval_limit": 5,
            "use_rerank": True,
            "use_mmr": True,
            "mmr_lambda": 0.7,
            "use_feedback_boost": True,
            "compress_chunks": False,
            "include_history": True,
            "history_k": 10,
            "include_ltm": True,
            "learn": True,
        }
        
        # Apply persona if provided
        if persona_id:
            persona = self.get_persona(persona_id)
            if persona:
                config.update({
                    "temperature": persona.llm.temperature,
                    "max_tokens": persona.llm.max_tokens,
                    "use_rag": persona.rag.enabled,
                    "retrieval_limit": persona.rag.retrieval_limit,
                    "use_rerank": persona.rag.use_rerank,
                    "use_mmr": persona.rag.use_mmr,
                    "mmr_lambda": persona.rag.mmr_lambda,
                    "use_feedback_boost": persona.rag.use_feedback_boost,
                    "compress_chunks": persona.rag.compress_chunks,
                    "include_history": persona.memory.include_history,
                    "history_k": persona.memory.history_k,
                    "include_ltm": persona.memory.include_ltm,
                    "learn": persona.feedback.auto_learn,
                })
        
        # Apply persona overrides
        if overrides:
            override_dict = overrides.dict(exclude_none=True)
            for key, value in override_dict.items():
                if key != "extra" and value is not None:
                    config[key] = value
            
            if overrides.extra:
                config.update(overrides.extra)
        
        # Apply direct request params (highest priority)
        if request_params:
            for key, value in request_params.items():
                if value is not None:
                    config[key] = value
        
        return config
    
    # =========================================================================
    # STATS
    # =========================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Get persona statistics."""
        return {
            "default_count": len(self._personas),
            "custom_count": len(self._custom_personas),
            "total_count": len(self._personas) + len(self._custom_personas),
            "default_ids": list(self._personas.keys()),
            "custom_ids": list(self._custom_personas.keys())
        }


# =============================================================================
# FACTORY
# =============================================================================

_persona_service: Optional[PersonaService] = None


def get_persona_service() -> PersonaService:
    """Get or create the singleton PersonaService instance."""
    global _persona_service
    if _persona_service is None:
        _persona_service = PersonaService()
    return _persona_service


def set_persona_service(service: PersonaService):
    """Set the PersonaService instance (for testing/DI)."""
    global _persona_service
    _persona_service = service
