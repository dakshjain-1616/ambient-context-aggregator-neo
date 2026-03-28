"""Watchdog-based file watcher for tracking developer file activity."""

import os
import time
import threading
from pathlib import Path
from typing import Callable, List, Dict, Optional

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler


WATCHED_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".kt",
    ".c", ".cpp", ".h", ".hpp", ".rb", ".php", ".swift", ".cs",
    ".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".ini", ".cfg",
    ".sh", ".bash", ".zsh", ".sql", ".html", ".css", ".scss",
}


class AmbientFileHandler(FileSystemEventHandler):
    """Handles filesystem events and records relevant code-file changes."""

    def __init__(
        self,
        callback: Optional[Callable] = None,
        extensions: Optional[set] = None,
    ):
        super().__init__()
        self.callback = callback
        self.extensions = extensions if extensions is not None else WATCHED_EXTENSIONS
        self.recent_changes: List[Dict] = []
        self._lock = threading.Lock()

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path, "moved")

    def _handle(self, src_path: str, action: str):
        path = Path(src_path)
        if path.suffix not in self.extensions:
            return
        # Skip hidden dirs / __pycache__ / .git
        parts = path.parts
        if any(p.startswith(".") or p == "__pycache__" for p in parts):
            return
        entry = {"action": action, "path": str(path), "timestamp": time.time()}
        with self._lock:
            self.recent_changes.append(entry)
            if len(self.recent_changes) > 200:
                self.recent_changes = self.recent_changes[-200:]
        if self.callback:
            try:
                self.callback(action, str(path))
            except Exception:
                pass

    def get_recent_changes(self, limit: int = 20) -> List[Dict]:
        with self._lock:
            return list(self.recent_changes[-limit:])


class FileWatcher:
    """Watches a directory tree for file changes."""

    def __init__(
        self,
        watch_path: str = ".",
        context_manager=None,
        extensions: Optional[set] = None,
    ):
        self.watch_path = os.path.abspath(watch_path)
        self.context_manager = context_manager
        self.handler = AmbientFileHandler(
            callback=self._on_change,
            extensions=extensions,
        )
        self.observer = Observer()
        self._running = False

    def _on_change(self, action: str, path: str):
        if self.context_manager:
            try:
                self.context_manager.signal_file_change(action, path)
            except Exception:
                pass

    def start(self):
        if self._running:
            return
        self.observer.schedule(self.handler, self.watch_path, recursive=True)
        self.observer.start()
        self._running = True

    def stop(self):
        if self._running:
            self.observer.stop()
            self.observer.join()
            self._running = False

    def get_recent_changes(self, limit: int = 20) -> List[Dict]:
        return self.handler.get_recent_changes(limit)

    @property
    def is_running(self) -> bool:
        return self._running
