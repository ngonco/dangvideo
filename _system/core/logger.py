import os
import sys
import logging
import asyncio
from datetime import datetime
from typing import List, Dict, Any, Callable

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    try:
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

class UILogger:
    def __init__(self, max_history: int = 500):
        self.max_history = max_history
        self.logs: List[Dict[str, Any]] = []
        self.subscribers: List[asyncio.Queue] = []
        
        # Setup Python standard logger
        self.logger = logging.getLogger("AutoVideoPoster")
        self.logger.setLevel(logging.INFO)
        if not self.logger.handlers:
            try:
                stream = sys.stdout if sys.stdout is not None else open(os.devnull, "w")
                handler = logging.StreamHandler(stream)
                formatter = logging.Formatter('[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%H:%M:%S')
                handler.setFormatter(formatter)
                self.logger.addHandler(handler)
            except Exception:
                pass

    def log(self, message: str, level: str = "INFO", category: str = "SYSTEM"):
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = {
            "time": timestamp,
            "message": message,
            "level": level.upper(),
            "category": category.upper()
        }
        
        # Add to in-memory history
        self.logs.append(log_entry)
        if len(self.logs) > self.max_history:
            self.logs.pop(0)

        # Print to console safely
        try:
            if level.upper() == "ERROR":
                self.logger.error(f"[{category}] {message}")
            elif level.upper() == "WARNING":
                self.logger.warning(f"[{category}] {message}")
            else:
                self.logger.info(f"[{category}] {message}")
        except Exception:
            pass

        # Broadcast to active WebSocket queues
        for queue in list(self.subscribers):
            try:
                queue.put_nowait(log_entry)
            except Exception:
                pass

    def info(self, message: str, category: str = "SYSTEM"):
        self.log(message, "INFO", category)

    def success(self, message: str, category: str = "SYSTEM"):
        self.log(message, "SUCCESS", category)

    def warning(self, message: str, category: str = "WARNING"):
        self.log(message, "WARNING", category)

    def error(self, message: str, category: str = "ERROR"):
        self.log(message, "ERROR", category)

    def subscribe(self) -> asyncio.Queue:
        queue = asyncio.Queue()
        self.subscribers.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue):
        if queue in self.subscribers:
            self.subscribers.remove(queue)

    def get_recent_logs(self) -> List[Dict[str, Any]]:
        return self.logs.copy()

logger = UILogger()
