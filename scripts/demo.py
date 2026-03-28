#!/usr/bin/env python3
"""
Ambient Context Aggregator — Demo Script

Simulates a realistic developer session: creates a git workspace, records file
changes, scrapes commits, parses terminal history, then compresses everything
into a context summary.

Works in mock mode when ANTHROPIC_API_KEY is not set.
Always writes output files to outputs/.
"""

import os
import sys
import json
import time
import shutil
import tempfile
from pathlib import Path
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()

OUTPUTS_DIR = Path("outputs")

# ── Demo workspace content ─────────────────────────────────────────────────────

DEMO_FILES = [
    (
        "main.py",
        '''#!/usr/bin/env python3
"""Entry point for the demo project."""
import argparse
from api import create_app

def main():
    parser = argparse.ArgumentParser(description="Demo API server")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    app.run(host="0.0.0.0", port=args.port, debug=args.debug)

if __name__ == "__main__":
    main()
''',
    ),
    (
        "api.py",
        '''"""REST API layer."""
from fastapi import FastAPI, HTTPException
from models import Item, ItemCreate
from storage import Storage

def create_app() -> FastAPI:
    app = FastAPI(title="Demo API", version="1.2.0")
    storage = Storage()

    @app.get("/health")
    def health():
        return {"status": "ok"}

    @app.get("/items")
    def list_items():
        return {"items": storage.all(), "total": len(storage.all())}

    @app.post("/items")
    def create_item(payload: ItemCreate):
        item = storage.create(payload)
        return item

    @app.get("/items/{item_id}")
    def get_item(item_id: int):
        item = storage.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Not found")
        return item

    return app
''',
    ),
    (
        "models.py",
        '''"""Pydantic data models."""
from dataclasses import dataclass, field
from typing import Optional
import time

@dataclass
class ItemCreate:
    name: str
    value: float
    tags: list = field(default_factory=list)

@dataclass
class Item:
    id: int
    name: str
    value: float
    tags: list
    created_at: float = field(default_factory=time.time)
    updated_at: Optional[float] = None

    def update(self, **kwargs):
        for k, v in kwargs.items():
            if hasattr(self, k):
                setattr(self, k, v)
        self.updated_at = time.time()
        return self
''',
    ),
    (
        "storage.py",
        '''"""In-memory storage layer."""
from typing import Optional
from models import Item, ItemCreate

class Storage:
    def __init__(self):
        self._store: dict = {}
        self._next_id = 1

    def all(self) -> list:
        return list(self._store.values())

    def get(self, item_id: int) -> Optional[Item]:
        return self._store.get(item_id)

    def create(self, payload: ItemCreate) -> Item:
        item = Item(
            id=self._next_id,
            name=payload.name,
            value=payload.value,
            tags=payload.tags,
        )
        self._store[self._next_id] = item
        self._next_id += 1
        return item

    def delete(self, item_id: int) -> bool:
        if item_id in self._store:
            del self._store[item_id]
            return True
        return False
''',
    ),
    (
        "tests/test_api.py",
        '''"""API integration tests."""
import pytest
from fastapi.testclient import TestClient
from api import create_app

@pytest.fixture
def client():
    return TestClient(create_app())

def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"

def test_create_and_get_item(client):
    r = client.post("/items", json={"name": "widget", "value": 9.99, "tags": ["tool"]})
    assert r.status_code == 200
    item = r.json()
    assert item["name"] == "widget"

    r2 = client.get(f"/items/{item["id"]}")
    assert r2.status_code == 200

def test_item_not_found(client):
    r = client.get("/items/999999")
    assert r.status_code == 404
''',
    ),
    (
        "config.py",
        '''"""Configuration management."""
import os
from dataclasses import dataclass

@dataclass
class Config:
    host: str = os.getenv("APP_HOST", "0.0.0.0")
    port: int = int(os.getenv("APP_PORT", "8000"))
    debug: bool = os.getenv("DEBUG", "false").lower() == "true"
    db_url: str = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    secret_key: str = os.getenv("SECRET_KEY", "change-me-in-production")
    log_level: str = os.getenv("LOG_LEVEL", "INFO")

config = Config()
''',
    ),
]

COMMIT_SEQUENCE = [
    ("Initial project scaffold", ["main.py"]),
    ("Add REST API with FastAPI", ["api.py"]),
    ("Define Item and ItemCreate models", ["models.py"]),
    ("Implement in-memory storage layer", ["storage.py"]),
    ("Add integration test suite", ["tests/test_api.py"]),
    ("Add configuration management", ["config.py"]),
    ("Fix pagination in list_items endpoint", ["api.py"]),
    ("Add input validation to ItemCreate", ["models.py"]),
    ("Improve error messages for 404 responses", ["api.py"]),
    ("Add DELETE /items/{id} endpoint", ["api.py"]),
]

SIMULATED_COMMANDS = [
    "git status",
    "git diff HEAD~1",
    "python -m pytest tests/ -v",
    "pip install fastapi uvicorn",
    "git commit -m 'Fix pagination in list_items endpoint'",
    "python main.py --debug",
    "grep -r 'def create' .",
    "cat api.py",
    "vim models.py",
    "git log --oneline -10",
    "docker build -t demo-api .",
    "python -c 'from api import create_app; print(create_app())'",
    "git push origin main",
    "pip freeze > requirements.txt",
    "curl localhost:8000/health",
    "ls -la",
    "make test",
    "black . && isort .",
    "mypy main.py api.py models.py",
    "uvicorn api:app --reload --port 8000",
    "python -m pytest --cov=. --cov-report=html",
    "git checkout -b feature/delete-endpoint",
    "git merge main --no-ff",
    "htop",
    "tail -f app.log",
    "docker-compose up -d",
    "psql $DATABASE_URL -c '\\dt'",
    "git stash && git pull && git stash pop",
    "pytest tests/test_api.py::test_health -v",
    "flake8 . --max-line-length=100",
]


# ── Setup helpers ──────────────────────────────────────────────────────────────

def setup_demo_workspace(workspace_dir: Path):
    """Create a git repo with multiple commits simulating real dev work."""
    import git

    workspace_dir.mkdir(parents=True, exist_ok=True)
    (workspace_dir / "tests").mkdir(exist_ok=True)

    repo = git.Repo.init(str(workspace_dir))
    with repo.config_writer() as cw:
        cw.set_value("user", "name", "Dev Demo")
        cw.set_value("user", "email", "dev@example.com")

    file_map = {name: content for name, content in DEMO_FILES}

    for msg, filenames in COMMIT_SEQUENCE:
        changed = False
        for fname in filenames:
            if fname in file_map:
                fpath = workspace_dir / fname
                fpath.parent.mkdir(parents=True, exist_ok=True)
                fpath.write_text(file_map[fname])
                repo.index.add([fname])
                changed = True
        if changed:
            repo.index.commit(msg)

    return repo


def simulate_terminal_history() -> list:
    """Return a list of plausible terminal command dicts."""
    now = time.time()
    return [
        {"command": cmd, "timestamp": now - (i + 1) * 90}
        for i, cmd in enumerate(SIMULATED_COMMANDS)
    ]


# ── Main demo ──────────────────────────────────────────────────────────────────

def run_demo():
    console.print(
        Panel.fit(
            "[bold cyan]Ambient Context Aggregator[/bold cyan]\n"
            "[dim]Simulating developer workflow → generating context summary[/dim]",
            border_style="cyan",
        )
    )

    OUTPUTS_DIR.mkdir(exist_ok=True)
    workspace_dir = Path(tempfile.mkdtemp(prefix="ambient_demo_"))
    demo_db = tempfile.mktemp(suffix=".db")

    try:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
            transient=False,
        ) as progress:

            # 1. Git workspace
            t = progress.add_task("Creating demo git repository…", total=None)
            repo = setup_demo_workspace(workspace_dir)
            progress.update(t, description=f"[green]✓[/green] Demo git repo ({len(COMMIT_SEQUENCE)} commits)")

            # 2. Database
            t = progress.add_task("Initialising SQLite database…", total=None)
            os.environ["DB_PATH"] = demo_db
            from ambient_context_aggr.database import (
                init_db, insert_file_event, insert_terminal_commands, insert_git_commits,
            )
            init_db()
            progress.update(t, description="[green]✓[/green] Database initialised")

            # 3. File events
            t = progress.add_task("Recording file change events…", total=None)
            py_files = list(workspace_dir.rglob("*.py"))
            for f in py_files:
                insert_file_event(str(f), "modified")
            progress.update(t, description=f"[green]✓[/green] {len(py_files)} file events recorded")

            # 4. Git commits
            t = progress.add_task("Scraping git commit history…", total=None)
            from ambient_context_aggr.git_scraper import get_repo_commits
            commits = get_repo_commits(repo_path=str(workspace_dir), limit=10)
            insert_git_commits(commits)
            progress.update(t, description=f"[green]✓[/green] {len(commits)} commits scraped")

            # 5. Terminal history
            t = progress.add_task("Parsing terminal history…", total=None)
            from ambient_context_aggr.history_parser import get_recent_commands
            simulated = simulate_terminal_history()
            real_cmds = get_recent_commands(limit=50)
            all_cmds = (simulated + real_cmds)[:80]
            insert_terminal_commands(all_cmds)
            progress.update(t, description=f"[green]✓[/green] {len(all_cmds)} commands indexed")

            # 6. Context compression
            t = progress.add_task("Compressing context…", total=None)
            from ambient_context_aggr.compressor import get_or_generate_context, build_signals_dict
            use_mock = not bool(os.getenv("ANTHROPIC_API_KEY"))
            ctx = get_or_generate_context(force_refresh=True, use_mock=use_mock)
            signals = build_signals_dict()
            progress.update(
                t,
                description=(
                    f"[green]✓[/green] Context ready "
                    f"(~{ctx['token_estimate']} tokens, "
                    f"{'mock' if use_mock else 'Claude'})"
                ),
            )

        # Display context
        console.print()
        console.print(
            Panel(
                ctx["summary"],
                title=(
                    f"[bold green]Context Summary[/bold green]  "
                    f"~{ctx['token_estimate']} tokens"
                ),
                border_style="green",
                padding=(1, 2),
            )
        )

        # ── Save outputs ───────────────────────────────────────────────────────
        console.print("\n[bold]Saving output files…[/bold]")

        mode_label = "Mock mode (no API key)" if use_mock else "AI-powered (Claude)"

        # outputs/demo_context.md
        ctx_path = OUTPUTS_DIR / "demo_context.md"
        ctx_path.write_text(
            f"# Ambient Context Aggregator — Demo Output\n\n"
            f"**Generated:** {datetime.now().isoformat()}  \n"
            f"**Mode:** {mode_label}  \n"
            f"**Token estimate:** ~{ctx['token_estimate']}  \n\n"
            f"---\n\n"
            f"{ctx['summary']}\n\n"
            f"---\n"
            f"*Generated by [Ambient Context Aggregator](https://github.com/dakshjain-1616/ambient-context-aggregator) demo*\n"
        )
        console.print(f"  [green]✓[/green] {ctx_path}")

        # outputs/demo_signals.json
        signals_out = {
            "generated_at": datetime.now().isoformat(),
            "mode": "mock" if use_mock else "ai",
            "stats": {
                "file_events": len(signals.get("file_events", [])),
                "git_commits": len(signals.get("git_commits", [])),
                "terminal_commands": len(signals.get("terminal_commands", [])),
                "token_estimate": ctx["token_estimate"],
            },
            "file_events": signals.get("file_events", [])[:10],
            "git_commits": signals.get("git_commits", [])[:10],
            "terminal_commands": signals.get("terminal_commands", [])[:20],
            "context_summary": {
                "text": ctx["summary"],
                "token_estimate": ctx["token_estimate"],
            },
        }
        sig_path = OUTPUTS_DIR / "demo_signals.json"
        sig_path.write_text(json.dumps(signals_out, indent=2, default=str))
        console.print(f"  [green]✓[/green] {sig_path}")

        console.print(f"\n[bold cyan]Demo complete![/bold cyan]")
        console.print("\n[dim]Next steps:[/dim]")
        console.print("  • [cyan]python -m ambient_context watch[/cyan]   — start background watcher")
        console.print("  • [cyan]python -m ambient_context get[/cyan]     — get context in terminal")
        console.print("  • [cyan]python app.py[/cyan]                     — Gradio dashboard")

    finally:
        # Clean up temp resources
        for p in [demo_db, workspace_dir]:
            try:
                if Path(str(p)).is_dir():
                    shutil.rmtree(str(p))
                elif Path(str(p)).exists():
                    os.unlink(str(p))
            except Exception:
                pass


if __name__ == "__main__":
    run_demo()
