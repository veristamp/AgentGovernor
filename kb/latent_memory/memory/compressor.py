# latent_memory/memory/compressor.py
"""
Memory Compressor - LLM-Powered Summarization.

Compresses multiple conversation turns into concise memories
for long-term storage while preserving key information.
"""

from typing import List, Dict, Any, Optional
from datetime import datetime

from .models import Turn, Memory, MemoryConfig
from config import get_logger

logger = get_logger("latent_memory.memory.compressor")

# =============================================================================
# COMPRESSION PROMPTS
# =============================================================================

COMPRESSION_SYSTEM_PROMPT = """You are a conversation summarizer. Your job is to compress conversation turns into a concise memory that preserves:
1. Key topics discussed
2. Important decisions made
3. Code or technical details mentioned
4. Questions asked and answers given

Be concise but don't lose important information."""

COMPRESSION_USER_TEMPLATE = """Summarize these conversation turns into a brief memory (2-3 sentences max):

{turns}

Output format:
SUMMARY: <your summary>
TOPICS: <comma-separated list of topics>"""

class MemoryCompressor:
    """
    Compresses conversation turns into compact memories.
    
    Uses LLM to summarize while preserving key information.
    Falls back to extractive summarization if no LLM available.
    """
    
    def __init__(
        self,
        llm_client=None,  # Optional: LLM client for abstractive summarization
        config: Optional[MemoryConfig] = None,
        model_name: str = "gpt-4o-mini"
    ):
        """
        Initialize compressor.
        
        Args:
            llm_client: Optional LLM client (e.g., OpenAI)
            config: Memory configuration
            model_name: Model to use for summarization
        """
        self.llm = llm_client
        self.config = config or MemoryConfig()
        self.model_name = model_name
    
    async def compress(
        self,
        turns: List[Turn],
        session_id: str,
        user_id: Optional[str] = None
    ) -> Memory:
        """
        Compress multiple turns into a single memory.
        
        Args:
            turns: Turns to compress
            session_id: Source session
            user_id: Optional user for cross-session LTM
            
        Returns:
            A Memory object containing the compressed information
        """
        if not turns:
            raise ValueError("No turns to compress")
        
        # Try LLM compression first
        if self.llm:
            summary, topics = await self._llm_compress(turns)
        else:
            summary, topics = self._extractive_compress(turns)
        
        # Calculate token savings
        original_tokens = sum(t.token_count for t in turns)
        compressed_tokens = len(summary) // 4
        
        # Compute aggregate importance
        avg_importance = sum(t.importance for t in turns) / len(turns)
        
        memory = Memory(
            session_id=session_id,
            user_id=user_id,
            summary=summary,
            turn_ids=[t.id for t in turns if t.id],
            turn_range=(
                min(t.id for t in turns if t.id) if any(t.id for t in turns) else 0,
                max(t.id for t in turns if t.id) if any(t.id for t in turns) else 0
            ),
            topics=topics,
            created_at=datetime.utcnow(),
            importance=avg_importance,
            original_token_count=original_tokens,
            compressed_token_count=compressed_tokens
        )
        
        logger.info(
            f"📦 Compressed {len(turns)} turns → {memory.compression_ratio()*100:.1f}% smaller "
            f"({original_tokens} → {compressed_tokens} tokens)"
        )
        
        return memory
    
    async def _llm_compress(self, turns: List[Turn]) -> tuple[str, List[str]]:
        """Use LLM to generate abstractive summary."""
        # Format turns for the prompt
        turns_text = "\n\n".join([
            f"[{t.role.upper()}]: {t.content[:500]}..."
            if len(t.content) > 500 else f"[{t.role.upper()}]: {t.content}"
            for t in turns
        ])
        
        prompt = COMPRESSION_USER_TEMPLATE.format(turns=turns_text)
        
        try:
            response = await self.llm.chat.completions.create(
                model=self.model_name,
                messages=[
                    {"role": "system", "content": COMPRESSION_SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=200,
                temperature=0.3
            )
            
            result = response.choices[0].message.content
            
            # Parse response
            summary = ""
            topics = []
            
            for line in result.split("\n"):
                if line.startswith("SUMMARY:"):
                    summary = line.replace("SUMMARY:", "").strip()
                elif line.startswith("TOPICS:"):
                    topics_str = line.replace("TOPICS:", "").strip()
                    topics = [t.strip() for t in topics_str.split(",")]
            
            return summary or result, topics
            
        except Exception as e:
            logger.warning(f"LLM compression failed: {e}, falling back to extractive")
            return self._extractive_compress(turns)
    
    def _extractive_compress(self, turns: List[Turn]) -> tuple[str, List[str]]:
        """
        Fallback: Create summary by extracting key sentences.
        
        No LLM required - uses heuristics.
        """
        # Extract key content from each turn
        key_parts = []
        topics = set()
        
        for turn in turns:
            # Get first sentence or first 100 chars
            content = turn.content.strip()
            
            if "." in content[:150]:
                first_sentence = content[:content.index(".") + 1]
            else:
                first_sentence = content[:100] + "..."
            
            # Add role prefix
            if turn.role == "user":
                key_parts.append(f"User asked: {first_sentence}")
            else:
                key_parts.append(f"Assistant: {first_sentence}")
            
            # Extract potential topics (capitalized words, code terms)
            words = content.split()
            for word in words:
                # Capitalized non-sentence-start words
                if word[0].isupper() and len(word) > 3:
                    topics.add(word.strip(".,!?:;"))
                # Code-like terms
                if "_" in word or word.startswith("@"):
                    topics.add(word.strip(".,!?:;"))
        
        summary = " | ".join(key_parts[:5])  # Max 5 key parts
        
        return summary, list(topics)[:10]  # Max 10 topics
    
    def estimate_compression(self, turns: List[Turn]) -> Dict[str, Any]:
        """
        Estimate compression without actually running it.
        
        Useful for UI to show potential savings.
        """
        original_tokens = sum(t.token_count for t in turns)
        
        # Estimate: typical compression is 80-90%
        estimated_tokens = max(50, original_tokens // 8)
        
        return {
            "turn_count": len(turns),
            "original_tokens": original_tokens,
            "estimated_tokens": estimated_tokens,
            "estimated_savings": original_tokens - estimated_tokens,
            "estimated_ratio": 1.0 - (estimated_tokens / original_tokens) if original_tokens else 0
        }
