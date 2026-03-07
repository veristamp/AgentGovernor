# services/watcher_service.py
"""
Watcher Service - Auto-Syncing Service for the Knowledge Base.

A toggleable background service that:
1. Watches configured directories for file changes
2. Triggers re-ingestion when files are modified/created
3. Prunes deleted files from the knowledge base
4. Keeps Postgres, Qdrant, and files in sync

Architecture:
    ┌──────────────────────────────────────────────────────────────┐
    │                     WatcherService                            │
    │                  (Toggleable Daemon)                          │
    │                          │                                    │
    │                          ▼                                    │
    │              ┌────────────────────────┐                       │
    │              │   IngestionService     │  ← Uses for sync      │
    │              │   (Scanner + Worker)   │                       │
    │              └────────────────────────┘                       │
    │                          │                                    │
    │              ┌───────────┴────────────┐                       │
    │              ▼                        ▼                       │
    │          Postgres                  Qdrant                     │
    │         (chunks)                (vectors)                    │
    └──────────────────────────────────────────────────────────────┘

    File Change → Event → Debounce → IngestionService.ingest_file()
                                            ↓
                                    Postgres + Qdrant synced!
"""

import asyncio
import time
import threading
import queue
import fnmatch
from pathlib import Path
from typing import Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from datetime import datetime

from config import get_logger

logger = get_logger("WatcherService")


# =============================================================================
# CONFIGURATION
# =============================================================================

@dataclass
class WatcherConfig:
    """Configuration for the watcher service."""
    watch_paths: List[str] = field(default_factory=lambda: ["."])
    patterns: List[str] = field(default_factory=lambda: ["*.py", "*.md", "*.ts", "*.tsx"])
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "__pycache__/*", "*.pyc", ".git/*", "*.tmp",
        "node_modules/*", ".venv/*", "*.egg-info/*",
        ".staging/*", "*.lock"
    ])
    debounce_seconds: float = 2.0
    prune_deleted: bool = True


@dataclass
class WatcherStats:
    """Runtime statistics."""
    files_processed: int = 0
    files_deleted: int = 0
    chunks_created: int = 0
    errors: int = 0
    start_time: datetime = field(default_factory=datetime.now)
    last_event: Optional[datetime] = None
    
    def uptime(self) -> str:
        delta = datetime.now() - self.start_time
        hours, remainder = divmod(delta.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        return f"{hours}h {minutes}m {seconds}s"
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "files_processed": self.files_processed,
            "files_deleted": self.files_deleted,
            "chunks_created": self.chunks_created,
            "errors": self.errors,
            "uptime": self.uptime(),
            "last_event": self.last_event.isoformat() if self.last_event else None
        }


# =============================================================================
# EVENT HANDLER (with debouncing)
# =============================================================================

class FileEventHandler:
    """Handles file events with debouncing."""
    
    def __init__(self, config: WatcherConfig):
        self.config = config
        self._pending: Dict[str, tuple] = {}  # path -> (event_type, timestamp)
        self._lock = threading.Lock()
    
    def should_process(self, path: str) -> bool:
        """Check if file matches patterns and isn't ignored."""
        path_obj = Path(path)
        
        # Check ignore patterns
        for pattern in self.config.ignore_patterns:
            if fnmatch.fnmatch(str(path_obj), pattern):
                return False
            if fnmatch.fnmatch(path_obj.name, pattern):
                return False
        
        # Check include patterns
        for pattern in self.config.patterns:
            if fnmatch.fnmatch(path_obj.name, pattern):
                return True
        
        return False
    
    def on_modified(self, path: str):
        """Queue a modified event."""
        if self.should_process(path):
            self._schedule("modified", path)
    
    def on_created(self, path: str):
        """Queue a created event."""
        if self.should_process(path):
            self._schedule("created", path)
    
    def on_deleted(self, path: str):
        """Queue a deleted event."""
        if self.should_process(path):
            self._schedule("deleted", path)
    
    def _schedule(self, event_type: str, path: str):
        """Schedule event with debounce."""
        with self._lock:
            self._pending[path] = (event_type, time.time())
    
    def get_ready_events(self) -> List[tuple]:
        """Get events past the debounce window."""
        ready = []
        now = time.time()
        
        with self._lock:
            to_remove = []
            for path, (event_type, timestamp) in self._pending.items():
                if now - timestamp >= self.config.debounce_seconds:
                    ready.append((event_type, path))
                    to_remove.append(path)
            
            for path in to_remove:
                del self._pending[path]
        
        return ready


# =============================================================================
# WATCHER BACKENDS
# =============================================================================

def create_watchdog_observer(handler: FileEventHandler, paths: List[str]):
    """Create a watchdog observer if available."""
    try:
        from watchdog.observers import Observer
        from watchdog.events import FileSystemEventHandler
        
        class WatchdogBridge(FileSystemEventHandler):
            def __init__(self, handler: FileEventHandler):
                self.handler = handler
            
            def on_modified(self, event):
                if not event.is_directory:
                    self.handler.on_modified(event.src_path)
            
            def on_created(self, event):
                if not event.is_directory:
                    self.handler.on_created(event.src_path)
            
            def on_deleted(self, event):
                if not event.is_directory:
                    self.handler.on_deleted(event.src_path)
        
        observer = Observer()
        bridge = WatchdogBridge(handler)
        
        for path in paths:
            if Path(path).exists():
                observer.schedule(bridge, path, recursive=True)
                logger.info(f"👁️ Watching: {path}")
        
        return observer
        
    except ImportError:
        logger.warning("watchdog not installed - using polling fallback")
        return None


class PollingWatcher:
    """Fallback file watcher using polling."""
    
    def __init__(self, handler: FileEventHandler, paths: List[str], interval: float = 2.0):
        self.handler = handler
        self.paths = [Path(p) for p in paths if Path(p).exists()]
        self.interval = interval
        self._file_times: Dict[str, float] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
    
    def start(self):
        self._running = True
        self._scan_initial()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True)
        self._thread.start()
        for p in self.paths:
            logger.info(f"👁️ Polling: {p}")
    
    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
    
    def _scan_initial(self):
        for base in self.paths:
            for fp in base.rglob("*"):
                if fp.is_file():
                    try:
                        self._file_times[str(fp)] = fp.stat().st_mtime
                    except OSError:
                        pass
    
    def _poll_loop(self):
        while self._running:
            time.sleep(self.interval)
            self._check_changes()
    
    def _check_changes(self):
        current: Set[str] = set()
        
        for base in self.paths:
            for fp in base.rglob("*"):
                if fp.is_file():
                    path_str = str(fp)
                    current.add(path_str)
                    try:
                        mtime = fp.stat().st_mtime
                        if path_str not in self._file_times:
                            self.handler.on_created(path_str)
                        elif mtime > self._file_times[path_str]:
                            self.handler.on_modified(path_str)
                        self._file_times[path_str] = mtime
                    except OSError:
                        pass
        
        # Deleted files
        for path_str in set(self._file_times) - current:
            self.handler.on_deleted(path_str)
            del self._file_times[path_str]


# =============================================================================
# WATCHER SERVICE
# =============================================================================

class WatcherService:
    """
    Toggleable file watcher service.
    
    Watches directories for changes and syncs with the knowledge base
    using IngestionService.
    """
    
    def __init__(
        self,
        config: Optional[WatcherConfig] = None,
        ingestion_service: Optional[Any] = None
    ):
        self.config = config or WatcherConfig()
        self._ingestion_service = ingestion_service
        self.stats = WatcherStats()
        
        # Event handler
        self.handler = FileEventHandler(self.config)
        
        # Watcher backend (watchdog or polling)
        self._observer = None
        self._polling_watcher = None
        
        # State
        self._running = False
        self._task: Optional[asyncio.Task] = None
    
    @property
    def ingestion(self):
        """Lazy-load ingestion service."""
        if self._ingestion_service is None:
            from services.ingestion_service import IngestionService
            self._ingestion_service = IngestionService()
        return self._ingestion_service
    
    @property
    def is_running(self) -> bool:
        """Check if watcher is currently running."""
        return self._running
    
    async def start(
        self,
        watch_paths: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None
    ):
        """
        Start watching directories.
        
        Args:
            watch_paths: Override directories to watch
            patterns: Override file patterns
        """
        if self._running:
            logger.warning("Watcher already running")
            return
        
        # Update config if provided
        if watch_paths:
            self.config.watch_paths = watch_paths
        if patterns:
            self.config.patterns = patterns
        
        # Reset stats
        self.stats = WatcherStats()
        
        # Create watcher backend
        self._observer = create_watchdog_observer(
            self.handler, self.config.watch_paths
        )
        
        if self._observer is None:
            self._polling_watcher = PollingWatcher(
                self.handler, self.config.watch_paths
            )
        
        # Start backend
        if self._observer:
            self._observer.start()
        elif self._polling_watcher:
            self._polling_watcher.start()
        
        self._running = True
        
        # Start event processing loop
        self._task = asyncio.create_task(self._event_loop())
        
        logger.info("🌱 WatcherService started")
        logger.info(f"   Watching: {', '.join(self.config.watch_paths)}")
        logger.info(f"   Patterns: {', '.join(self.config.patterns)}")
    
    async def stop(self):
        """Stop watching directories."""
        if not self._running:
            return
        
        self._running = False
        
        # Stop backend
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None
        elif self._polling_watcher:
            self._polling_watcher.stop()
            self._polling_watcher = None
        
        # Cancel event loop
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        
        logger.info("🛑 WatcherService stopped")
        logger.info(f"   Stats: {self.stats.to_dict()}")
    
    async def add_watch_path(self, path: str):
        """Add a new path to watch (requires restart)."""
        if path not in self.config.watch_paths:
            self.config.watch_paths.append(path)
            if self._running:
                await self.stop()
                await self.start()
    
    async def remove_watch_path(self, path: str):
        """Remove a path from watching (requires restart)."""
        if path in self.config.watch_paths:
            self.config.watch_paths.remove(path)
            if self._running:
                await self.stop()
                await self.start()
    
    def get_status(self) -> Dict[str, Any]:
        """Get current watcher status."""
        return {
            "running": self._running,
            "watch_paths": self.config.watch_paths,
            "patterns": self.config.patterns,
            "stats": self.stats.to_dict()
        }
    
    async def _event_loop(self):
        """Main event processing loop."""
        while self._running:
            try:
                events = self.handler.get_ready_events()
                
                for event_type, path in events:
                    await self._process_event(event_type, path)
                
                await asyncio.sleep(0.5)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.exception(f"Event loop error: {e}")
                self.stats.errors += 1
    
    async def _process_event(self, event_type: str, path: str):
        """Process a single file event."""
        self.stats.last_event = datetime.now()
        
        try:
            if event_type in ("modified", "created"):
                await self._handle_file_change(path)
            elif event_type == "deleted":
                await self._handle_file_delete(path)
                
        except Exception as e:
            logger.error(f"Failed to process {event_type} for {path}: {e}")
            self.stats.errors += 1
    
    async def _handle_file_change(self, path: str):
        """Handle file modification or creation."""
        logger.info(f"🌱 File changed: {path}")
        
        try:
            # Use IngestionService to re-ingest the file
            result = await self.ingestion.ingest_file(
                Path(path),
                wait_for_completion=True
            )
            
            if result.success:
                self.stats.files_processed += 1
                self.stats.chunks_created += result.data.get("chunks_created", 0)
                logger.info(f"   ✅ Synced: {result.data.get('chunks_created', 0)} chunks")
            else:
                self.stats.errors += 1
                logger.error(f"   ❌ Sync failed: {result.error}")
                
        except Exception as e:
            self.stats.errors += 1
            logger.exception(f"   ❌ Error: {e}")
    
    async def _handle_file_delete(self, path: str):
        """Handle file deletion."""
        if not self.config.prune_deleted:
            return
        
        logger.info(f"🗑️ File deleted: {path}")
        
        try:
            # Delete from Postgres and Qdrant
            # Use IngestionService or direct DB access
            await self._prune_file(path)
            self.stats.files_deleted += 1
            logger.info(f"   ✅ Pruned from KB")
            
        except Exception as e:
            self.stats.errors += 1
            logger.error(f"   ❌ Prune failed: {e}")
    
    async def _prune_file(self, path: str):
        """Remove a file's chunks from Postgres and Qdrant."""
        import asyncpg
        from config import DATABASE_CONFIG
        from qdrant_client import AsyncQdrantClient
        from qdrant_client.models import Filter, FieldCondition, MatchValue
        
        # Prune from Qdrant
        try:
            qdrant = AsyncQdrantClient(url=DATABASE_CONFIG.qdrant_url)
            await qdrant.delete(
                collection_name=DATABASE_CONFIG.qdrant_collection_chunks,
                points_selector=Filter(
                    must=[FieldCondition(
                        key="source",
                        match=MatchValue(value=Path(path).name)
                    )]
                )
            )
            await qdrant.close()
        except Exception as e:
            logger.warning(f"Qdrant prune failed: {e}")
        
        # Prune from Postgres
        try:
            conn = await asyncpg.connect(DATABASE_CONFIG.postgres_dsn)
            
            # Delete chunks
            await conn.execute("""
                DELETE FROM chunks 
                WHERE doc_id IN (
                    SELECT id FROM documents WHERE file_path LIKE $1
                )
            """, f"%{Path(path).name}")
            
            # Mark document as deleted
            await conn.execute("""
                UPDATE documents SET sync_status = 'deleted'
                WHERE file_path LIKE $1
            """, f"%{Path(path).name}")
            
            await conn.close()
        except Exception as e:
            logger.warning(f"Postgres prune failed: {e}")


# =============================================================================
# FACTORY
# =============================================================================

def create_watcher_service(
    watch_paths: Optional[List[str]] = None,
    patterns: Optional[List[str]] = None,
    **kwargs
) -> WatcherService:
    """
    Factory function for WatcherService.
    
    Usage:
        service = create_watcher_service(watch_paths=["doc/", "src/"])
        await service.start()
        # ... later
        await service.stop()
    """
    config = WatcherConfig()
    if watch_paths:
        config.watch_paths = watch_paths
    if patterns:
        config.patterns = patterns
    
    return WatcherService(config=config)
