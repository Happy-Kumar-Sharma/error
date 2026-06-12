import logging
from collections import deque
import threading
from typing import List, Optional

_global_handler: Optional["pyerrorLogHandler"] = None
_lock = threading.Lock()

class pyerrorLogHandler(logging.Handler):
    """
    Thread-safe logging handler that retains the last N formatted logs in memory.
    """
    def __init__(self, max_records: int = 20):
        super().__init__()
        self.records = deque(maxlen=max_records)
        self._records_lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            with self._records_lock:
                self.records.append(msg)
        except Exception:
            self.handleError(record)

    def get_logs(self) -> List[str]:
        with self._records_lock:
            return list(self.records)

    def clear(self) -> None:
        with self._records_lock:
            self.records.clear()

def integrate_logging(max_tail_lines: int = 20) -> pyerrorLogHandler:
    """
    Enables contextual log tail aggregation by attaching a memory-bounded
    log handler to the root logger.
    """
    global _global_handler
    with _lock:
        if _global_handler is not None:
            return _global_handler
        
        _global_handler = pyerrorLogHandler(max_records=max_tail_lines)
        # Setup basic format if none exists
        formatter = logging.Formatter("[%(levelname)s] %(asctime)s - %(message)s")
        _global_handler.setFormatter(formatter)
        
        logging.getLogger().addHandler(_global_handler)
        return _global_handler

def get_recent_logs() -> List[str]:
    """Retrieves the currently captured list of logs."""
    if _global_handler is None:
        return []
    return _global_handler.get_logs()
