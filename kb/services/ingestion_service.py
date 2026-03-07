# services/ingestion_service.py
"""
Ingestion Service - High-level API for document ingestion.

This is the service layer for ingestion operations. It:
1. Creates and manages IngestionManager internally
2. Provides consistent response formatting
3. Handles errors gracefully
4. Exposes ingestion operations to API endpoints and CLI

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                     IngestionService                          │
    │            (API formatting + Error handling)                  │
    │                           │                                   │
    │                           ▼                                   │
    │              ┌────────────────────────┐                       │
    │              │   IngestionManager     │  ← Created internally │
    │              │  (Scanner + Worker)    │                       │
    │              └────────────────────────┘                       │
    └──────────────────────────────────────────────────────────────┘
"""

import time
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional, Union
from dataclasses import dataclass

from config import get_logger, DATABASE_CONFIG

logger = get_logger("IngestionService")


@dataclass
class IngestionResponse:
    """Standardized response from ingestion operations."""
    success: bool
    operation: str
    data: Dict[str, Any]
    error: Optional[str] = None
    duration_ms: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "operation": self.operation,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms
        }


class IngestionService:
    """
    Ingestion service providing high-level ingestion operations.
    
    This service wraps IngestionManager and provides:
    - Consistent response formatting
    - Error handling
    - Config management
    
    Usage:
        service = IngestionService()
        
        # Ingest a file
        result = await service.ingest_file(Path("doc/example.md"))
        
        # Ingest a directory
        result = await service.ingest_directory(Path("doc/"))
        
        # Get status
        status = await service.get_status()
        
        # Run maintenance
        result = await service.run_maintenance()
    """
    
    def __init__(
        self,
        doc_dir: Optional[Path] = None,
        extensions: Optional[List[str]] = None,
        enable_concepts: bool = True,
        enable_sparse: bool = True,
        # Legacy parameters (ignored - use DATABASE_CONFIG)
        postgres_dsn: Optional[str] = None,
        qdrant_url: Optional[str] = None,
        collection_name: Optional[str] = None
    ):
        """
        Initialize ingestion service.
        
        Database config comes from DATABASE_CONFIG (single source of truth).
        
        Args:
            doc_dir: Default document directory
            extensions: File extensions to process
            enable_concepts: Enable GLiNER concept extraction
            enable_sparse: Enable BM25 sparse vectors
        """
        self._doc_dir = doc_dir or Path("doc")
        self._extensions = set(extensions) if extensions else {".md", ".py", ".ts", ".tsx", ".html"}
        self._enable_concepts = enable_concepts
        self._enable_sparse = enable_sparse
        
        # Lazy-loaded manager
        self._manager = None
        
        logger.info(f"🚀 IngestionService initialized")
        logger.info(f"   Postgres: {DATABASE_CONFIG.postgres_dsn.split('@')[-1]}")
        logger.info(f"   Qdrant: {DATABASE_CONFIG.qdrant_url}")
        logger.info(f"   Collection: {DATABASE_CONFIG.qdrant_collection_chunks}")
    
    def _get_manager(self):
        """Get or create IngestionManager."""
        if self._manager is None:
            from ingestion import IngestionManager, IngestionConfig
            
            # IngestionConfig gets DB settings from DATABASE_CONFIG automatically
            config = IngestionConfig(
                doc_dir=self._doc_dir,
                extensions=self._extensions,
                enable_concept_harvesting=self._enable_concepts,
                enable_sparse_embeddings=self._enable_sparse
            )
            
            self._manager = IngestionManager(config)
            
        return self._manager
    
    async def ingest(
        self,
        target: Union[Path, List[Path], str, List[str]],
        recursive: bool = True,
        wait: bool = True,
    ) -> IngestionResponse:
        """
        Unified ingestion entry point.
        
        Handles:
        - Single file: ingest(Path("doc/readme.md"))
        - Multiple files: ingest([Path("a.md"), Path("b.py")])  
        - Directory: ingest(Path("doc/"), recursive=True)
        - String paths: ingest("doc/readme.md") or ingest(["a.md", "b.md"])
        
        Args:
            target: File path, list of file paths, or directory path
            recursive: If target is a directory, scan subdirectories
            wait: Wait for processing to complete
            
        Returns:
            IngestionResponse with operation result
        """
        start_time = time.time()
        request_id = f"ingest_{uuid.uuid4().hex[:8]}"
        
        # Normalize target for logging
        if isinstance(target, list):
            target_desc = f"{len(target)} files"
        else:
            target_desc = str(target)
        
        logger.info(f"📂 [{request_id}] Ingesting: {target_desc}")
        
        try:
            manager = self._get_manager()
            result = await manager.ingest(target, recursive=recursive, wait=wait)
            
            duration_ms = int((time.time() - start_time) * 1000)
            
            if result.success:
                logger.info(
                    f"✅ [{request_id}] Completed in {duration_ms}ms"
                )
                # result is now IngestionAnalytics
                summary = result.get_summary()
                return IngestionResponse(
                    success=True,
                    operation="ingest",
                    data=summary,
                    duration_ms=duration_ms
                )
            else:
                logger.error(f"❌ [{request_id}] Failed: {result.error}")
                return IngestionResponse(
                    success=False,
                    operation="ingest",
                    data={"target": target_desc},
                    error=result.error,
                    duration_ms=duration_ms
                )
                
        except Exception as e:
            logger.exception(f"❌ [{request_id}] Ingestion error")
            return IngestionResponse(
                success=False,
                operation="ingest",
                data={"target": target_desc},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
    
    # Convenience aliases (delegate to ingest)
    async def ingest_file(self, file_path: Path, wait: bool = True) -> IngestionResponse:
        """Alias for ingest() with a single file."""
        return await self.ingest(file_path, wait=wait)
    
    async def ingest_files(self, file_paths: List[Path], wait: bool = True) -> IngestionResponse:
        """Alias for ingest() with multiple files."""
        return await self.ingest(file_paths, wait=wait)
    
    async def ingest_directory(self, directory: Path = None, recursive: bool = True, wait: bool = True, **kwargs) -> IngestionResponse:
        """Alias for ingest() with a directory."""
        return await self.ingest(directory or self._doc_dir, recursive=recursive, wait=wait)
    
    async def get_status(self) -> IngestionResponse:
        """
        Get current ingestion pipeline status.
        
        Returns:
            IngestionResponse with queue and document statistics
        """
        start_time = time.time()
        
        try:
            manager = self._get_manager()
            status = await manager.get_status()
            
            # Simple conversion to dict for the frontend
            return IngestionResponse(
                success=True,
                operation="get_status",
                data={
                    "queue": {
                        "pending_chunking": status.pending_chunk_jobs,
                        "pending_indexing": status.pending_graph_jobs,
                        "processing": status.processing_jobs,
                        "failed": status.failed_jobs,
                        "total_pending": status.pending_chunk_jobs + status.pending_graph_jobs,
                    },
                    "documents": {
                        "total": status.total_documents,
                        "synced": status.synced_documents,
                        "stale": status.stale_documents,
                        "sync_rate": round(status.synced_documents / max(status.total_documents, 1) * 100, 1),
                    },
                    "chunks": {
                        "total": status.total_chunks,
                        "pending_indexing": status.pending_embeddings,
                    },
                    # New: Add stage names for frontend routing/UI reflection
                    "pipeline_stages": ["scan", "chunking", "concepts", "indexing"]
                },
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.exception("Failed to get status")
            return IngestionResponse(
                success=False,
                operation="get_status",
                data={},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
    
    async def list_documents(self, limit: int = 100) -> IngestionResponse:
        """
        List indexed documents.
        
        Returns:
            IngestionResponse with list of documents
        """
        start_time = time.time()
        
        try:
            manager = self._get_manager()
            documents = await manager.list_documents(limit=limit)
            
            return IngestionResponse(
                success=True,
                operation="list_documents",
                data=documents,
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.exception("Failed to list documents")
            return IngestionResponse(
                success=False,
                operation="list_documents",
                data=[],
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )

    
    async def process_pending(
        self,
        max_jobs: Optional[int] = None
    ) -> IngestionResponse:
        """
        Process pending jobs in the queue.
        
        Use this to process jobs stuck in pending state.
        
        Args:
            max_jobs: Maximum jobs to process (None = all)
            
        Returns:
            IngestionResponse with processing statistics
        """
        start_time = time.time()
        
        logger.info(f"⚙️ Processing pending jobs (max={max_jobs or 'all'})...")
        
        try:
            manager = self._get_manager()
            # manager.process_pending now returns IngestionAnalytics
            analytics = await manager.process_pending()
            
            duration_ms = int((time.time() - start_time) * 1000)
            summary = analytics.get_summary()
            
            logger.info(f"✅ Processed jobs in {duration_ms}ms")
            
            return IngestionResponse(
                success=True,
                operation="process_pending",
                data=summary,
                duration_ms=duration_ms
            )
            
        except Exception as e:
            logger.exception("Failed to process pending jobs")
            return IngestionResponse(
                success=False,
                operation="process_pending",
                data={},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
    
    async def retry_failed(self) -> IngestionResponse:
        """
        Retry all failed jobs.
        
        Returns:
            IngestionResponse with number of jobs reset
        """
        start_time = time.time()
        
        try:
            manager = self._get_manager()
            count = await manager.retry_failed()
            
            logger.info(f"🔄 Reset {count} failed jobs for retry")
            
            return IngestionResponse(
                success=True,
                operation="retry_failed",
                data={"jobs_reset": count},
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.exception("Failed to retry jobs")
            return IngestionResponse(
                success=False,
                operation="retry_failed",
                data={},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
    
    async def run_maintenance(
        self,
        synonym_threshold: float = 0.92,
        island_min_age_days: int = 7,
        supernode_threshold_percent: float = 0.10
    ) -> IngestionResponse:
        """
        Run graph maintenance (gardener).
        
        Performs:
        1. Synonym compaction (merge similar concepts)
        2. Island pruning (remove orphan concepts)
        3. Supernode demotion (reduce weight of overly-connected concepts)
        
        Args:
            synonym_threshold: Minimum similarity to merge (0.0-1.0)
            island_min_age_days: Days before pruning orphan concepts
            supernode_threshold_percent: % of graph to trigger demotion
            
        Returns:
            IngestionResponse with maintenance statistics
        """
        start_time = time.time()
        
        logger.info("🌱 Running graph maintenance...")
        
        try:
            manager = self._get_manager()
            stats = await manager.run_gardener(
                synonym_threshold=synonym_threshold,
                island_min_age_days=island_min_age_days,
                supernode_threshold_percent=supernode_threshold_percent
            )
            
            duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"✨ Maintenance complete in {duration_ms}ms: {stats}")
            
            return IngestionResponse(
                success=True,
                operation="run_maintenance",
                data={
                    "synonyms_merged": stats.get("synonyms_merged", 0),
                    "islands_pruned": stats.get("islands_pruned", 0),
                    "supernodes_demoted": stats.get("supernodes_demoted", 0),
                    "edges_processed": stats.get("edges_processed", 0),
                },
                duration_ms=duration_ms
            )
            
        except Exception as e:
            logger.exception("Maintenance failed")
            return IngestionResponse(
                success=False,
                operation="run_maintenance",
                data={},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )
    
    async def cancel_document(self, doc_id: int) -> IngestionResponse:
        """
        Cancel pending jobs for a specific document.
        
        Args:
            doc_id: Document ID to cancel jobs for
            
        Returns:
            IngestionResponse with number of jobs cancelled
        """
        start_time = time.time()
        
        try:
            manager = self._get_manager()
            count = await manager.cancel_jobs(doc_id)
            
            return IngestionResponse(
                success=True,
                operation="cancel_document",
                data={"doc_id": doc_id, "jobs_cancelled": count},
                duration_ms=int((time.time() - start_time) * 1000)
            )
            
        except Exception as e:
            logger.exception(f"Failed to cancel jobs for doc {doc_id}")
            return IngestionResponse(
                success=False,
                operation="cancel_document",
                data={"doc_id": doc_id},
                error=str(e),
                duration_ms=int((time.time() - start_time) * 1000)
            )


def create_ingestion_service(
    postgres_dsn: Optional[str] = None,
    qdrant_url: Optional[str] = None,
    **kwargs
) -> IngestionService:
    """
    Factory function for IngestionService.
    
    Usage:
        service = create_ingestion_service()
        result = await service.ingest_directory(Path("doc/"))
    """
    return IngestionService(
        postgres_dsn=postgres_dsn,
        qdrant_url=qdrant_url,
        **kwargs
    )
