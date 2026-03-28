"""File system watcher — monitors a directory for source-file changes using watchdog."""

import os
import time
import threading
from pathlib import Path

from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from .database import init_db, insert_file_event

# Extensions worth tracking
WATCH_EXTENSIONS = {
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".go", ".rs", ".java", ".cpp", ".c", ".h",
    ".md", ".yaml", ".yml", ".toml", ".json",
    ".sh", ".env", ".sql",
}

# Directories to always skip
SKIP_DIRS = {
    ".git", "__pycache__", "node_modules",
    ".venv", "venv", "env", ".tox", "dist", "build",
    ".mypy_cache", ".pytest_cache",
}


class ContextEventHandler(FileSystemEventHandler):
    """Watchdog event handler that stores file events in the database."""

    def __init__(self, callback=None):
        super().__init__()
        self.callback = callback
        self._recent: dict = {}
        self._lock = threading.Lock()

    def _should_track(self, path: str) -> bool:
        p = Path(path)
        if any(part in SKIP_DIRS for part in p.parts):
            return False
        return p.suffix.lower() in WATCH_EXTENSIONS

    def _debounce(self, path: str, cooldown: float = 0.5) -> bool:
        """Return True if enough time has passed since the last event for this path."""
        now = time.time()
        with self._lock:
            if now - self._recent.get(path, 0) < cooldown:
                return False
            self._recent[path] = now
        return True

    def _handle(self, path: str, event_type: str) -> None:
        if self._should_track(path) and self._debounce(path):
            insert_file_event(path, event_type)
            if self.callback:
                try:
                    self.callback(path, event_type)
                except Exception:
                    pass

    def on_created(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "created")

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "modified")

    def on_deleted(self, event):
        if not event.is_directory:
            self._handle(event.src_path, "deleted")

    def on_moved(self, event):
        if not event.is_directory:
            self._handle(event.dest_path, "moved")


class FileWatcher:
    """Manages a watchdog Observer for a given directory."""

    def __init__(self, watch_dir: str = None, callback=None):
        self.watch_dir = watch_dir or os.getenv("WATCH_DIR", ".")
        self.callback = callback
        self._observer = None  # type: Observer
        self._running = False

    def start(self) -> None:
        init_db()
        self._observer = Observer()
        handler = ContextEventHandler(callback=self.callback)
        self._observer.schedule(handler, self.watch_dir, recursive=True)
        self._observer.start()
        self._running = True

    def stop(self) -> None:
        if self._observer:
            self._observer.stop()
            self._observer.join()
        self._running = False

    def is_running(self) -> bool:
        return self._running and self._observer is not None and self._observer.is_alive()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args):
        self.stop()


def start_watcher(watch_dir: str = None, callback=None) -> FileWatcher:
    """Convenience function: create, start, and return a FileWatcher."""
    watcher = FileWatcher(watch_dir=watch_dir, callback=callback)
    watcher.start()
    return watcher
