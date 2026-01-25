# config/logging.py
"""
Central Logging Configuration.

Provides a unified, aesthetically pleasing logging setup across the entire codebase.
Uses 'rich' for enhanced console output with an interstellar theme.
"""

import os
import logging
import sys
from typing import Optional, Any, Union
from datetime import datetime

# Try to import rich components
try:
    from rich.console import Console
    from rich.logging import RichHandler
    from rich.theme import Theme
    from rich.panel import Panel
    from rich.table import Table
    from rich.text import Text
    from rich.traceback import install as install_rich_traceback
    HAS_RICH = True
except ImportError:
    HAS_RICH = False

# --- Constants & Configuration ---

DEFAULT_LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Custom Theme for a premium, industry-standard feel
if HAS_RICH:
    INTERSTELLAR_THEME = Theme({
        "info": "cyan",
        "warning": "bold yellow",
        "error": "bold red",
        "critical": "bold white on red",
        "success": "bold green",
        "timestamp": "dim white",
        "logger.name": "dim cyan",
        "logger.message": "white",
        "repr.path": "dim blue",
        "repr.filename": "blue",
    })
    # Initialize global console
    console = Console(theme=INTERSTELLAR_THEME)
else:
    INTERSTELLAR_THEME = None
    console = None

# Custom Logging Level: SUCCESS
SUCCESS_LEVEL_NUM = 25
logging.addLevelName(SUCCESS_LEVEL_NUM, "SUCCESS")

def _success_logger(self, message, *args, **kws):
    if self.isEnabledFor(SUCCESS_LEVEL_NUM):
        self._log(SUCCESS_LEVEL_NUM, message, args, **kws)

logging.Logger.success = _success_logger # type: ignore

class InterstellarLogger(logging.Logger):
    """
    Enhanced logger that provides convenience methods for beautiful CLI output.
    """
    def success(self, msg: str, *args, **kwargs):
        self._log(SUCCESS_LEVEL_NUM, msg, args, **kwargs)

    def panel(self, msg: str, title: Optional[str] = None, style: str = "cyan"):
        """Display a beautiful panel in the console."""
        if HAS_RICH and console:
            console.print(Panel(msg, title=title, border_style=style, expand=False))
        else:
            print(f"--- {title or ''} ---\n{msg}\n{'-' * 10}")

    def table(self, title: str, columns: list, rows: list, style: str = "magenta"):
        """Display a beautiful table in the console."""
        if HAS_RICH and console:
            table = Table(title=title, header_style=f"bold {style}")
            for col in columns:
                table.add_column(col)
            for row in rows:
                table.add_row(*[str(item) for item in row])
            console.print(table)
        else:
            print(f"\n[ {title} ]")
            print(" | ".join(columns))
            for row in rows:
                print(" | ".join([str(i) for i in row]))

# Register the custom logger class
logging.setLoggerClass(InterstellarLogger)

def setup_logging(
    level: str = DEFAULT_LOG_LEVEL,
    show_locals: bool = False,
    enable_traceback: bool = True
):
    """
    Configure project-wide logging.
    
    Uses rich for beautiful console logs with syntax highlighting, 
    custom themes, and enhanced tracebacks.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)
    
    # Force reconfiguration by removing existing handlers on the root logger
    root_logger = logging.getLogger()
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    if HAS_RICH:
        # Install beautiful tracebacks
        if enable_traceback:
            install_rich_traceback(show_locals=show_locals, console=console)
        
        # Initialize rich handler
        handler = RichHandler(
            level=log_level,
            console=console,
            show_time=True,
            omit_repeated_times=True,
            show_level=True,
            show_path=True,
            markup=True,
            rich_tracebacks=True,
            tracebacks_show_locals=show_locals,
            log_time_format="[%H:%M:%S]"
        )
        
        # Configure root logger
        root_logger.setLevel(log_level)
        root_logger.addHandler(handler)
    else:
        # Fallback to standard logging
        handler = logging.StreamHandler(sys.stdout)
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        handler.setFormatter(logging.Formatter(log_format, datefmt="%H:%M:%S"))
        root_logger.setLevel(log_level)
        root_logger.addHandler(handler)

def get_logger(name: str) -> InterstellarLogger:
    """Get a consistent logger for a specific module."""
    return logging.getLogger(name) # type: ignore

# Auto-setup on import if not already configured
if not logging.getLogger().hasHandlers():
    setup_logging()

