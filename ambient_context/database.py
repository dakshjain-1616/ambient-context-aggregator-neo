"""SQLite database layer for storing developer activity signals and context summaries."""

import os
import json
import time
import sqlite3
from pathlib import Path


def _default_db_path() -> str:
    return str(Path.home() / ".ambient_context" / "context.db")


def get_connection() -> sqlite3.Connection:
    db_path = os.getenv("DB_PATH", _default_db_path())
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    """Create all tables if they don't exist."""
    conn = get_connection()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS file_events (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT    NOT NULL,
            event_type  TEXT    NOT NULL,
            timestamp   REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS git_commits (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            hash        TEXT    UNIQUE NOT NULL,
            author      TEXT    NOT NULL,
            message     TEXT    NOT NULL,
            timestamp   REAL    NOT NULL,
            repo_path   TEXT    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS terminal_commands (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            command     TEXT    NOT NULL,
            timestamp   REAL    NOT NULL
        );

        CREATE TABLE IF NOT EXISTS context_summaries (
            id                  INTEGER PRIMARY KEY AUTOINCREMENT,
            summary             TEXT    NOT NULL,
            token_estimate      INTEGER NOT NULL,
            signals_json        TEXT    NOT NULL,
            created_at          REAL    NOT NULL,
            generation_time_ms  INTEGER DEFAULT 0,
            provider            TEXT    DEFAULT 'mock'
        );

        CREATE TABLE IF NOT EXISTS meeting_notes (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            path        TEXT    UNIQUE NOT NULL,
            title       TEXT    NOT NULL,
            excerpt     TEXT    NOT NULL DEFAULT '',
            word_count  INTEGER NOT NULL DEFAULT 0,
            modified_at REAL    NOT NULL,
            indexed_at  REAL    NOT NULL
        );
    """)
    # Add columns that may be missing in older databases (idempotent)
    for col, definition in [
        ("generation_time_ms", "INTEGER DEFAULT 0"),
        ("provider", "TEXT DEFAULT 'mock'"),
    ]:
        try:
            conn.execute(f"ALTER TABLE context_summaries ADD COLUMN {col} {definition}")
            conn.commit()
        except sqlite3.OperationalError:
            pass  # Column already exists
    conn.commit()
    conn.close()


# ── File events ────────────────────────────────────────────────────────────────

def insert_file_event(path: str, event_type: str) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO file_events (path, event_type, timestamp) VALUES (?, ?, ?)",
        (path, event_type, time.time()),
    )
    conn.commit()
    conn.close()


def get_recent_file_events(limit: int = 20, since_seconds: int = 3600) -> list:
    since = time.time() - since_seconds
    conn = get_connection()
    rows = conn.execute(
        "SELECT path, event_type, timestamp FROM file_events "
        "WHERE timestamp > ? ORDER BY timestamp DESC LIMIT ?",
        (since, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Git commits ────────────────────────────────────────────────────────────────

def insert_git_commits(commits: list) -> None:
    conn = get_connection()
    for c in commits:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO git_commits "
                "(hash, author, message, timestamp, repo_path) VALUES (?,?,?,?,?)",
                (c["hash"], c["author"], c["message"], c["timestamp"], c["repo_path"]),
            )
        except Exception:
            pass
    conn.commit()
    conn.close()


def get_recent_git_commits(limit: int = 10) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT hash, author, message, timestamp, repo_path FROM git_commits "
        "ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Terminal commands ──────────────────────────────────────────────────────────

def insert_terminal_commands(commands: list) -> None:
    conn = get_connection()
    for cmd in commands:
        conn.execute(
            "INSERT INTO terminal_commands (command, timestamp) VALUES (?, ?)",
            (cmd["command"], cmd.get("timestamp", time.time())),
        )
    conn.commit()
    conn.close()


def get_recent_terminal_commands(limit: int = 50) -> list:
    conn = get_connection()
    rows = conn.execute(
        "SELECT command, timestamp FROM terminal_commands ORDER BY timestamp DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Context summaries ──────────────────────────────────────────────────────────

def save_context_summary(
    summary: str,
    token_estimate: int,
    signals: dict,
    generation_time_ms: int = 0,
    provider: str = "mock",
) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO context_summaries "
        "(summary, token_estimate, signals_json, created_at, generation_time_ms, provider) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (
            summary,
            token_estimate,
            json.dumps(signals, default=str),
            time.time(),
            generation_time_ms,
            provider,
        ),
    )
    conn.commit()
    conn.close()


def get_latest_context_summary():
    conn = get_connection()
    row = conn.execute(
        "SELECT summary, token_estimate, signals_json, created_at, "
        "generation_time_ms, provider "
        "FROM context_summaries ORDER BY created_at DESC LIMIT 1"
    ).fetchone()
    conn.close()
    if row:
        result = dict(row)
        result["signals"] = json.loads(result["signals_json"])
        return result
    return None


def get_context_summary_history(limit: int = 10) -> list:
    """Return the *limit* most recent context summaries (newest first)."""
    conn = get_connection()
    rows = conn.execute(
        "SELECT summary, token_estimate, signals_json, created_at, "
        "generation_time_ms, provider "
        "FROM context_summaries ORDER BY created_at DESC LIMIT ?",
        (limit,),
    ).fetchall()
    conn.close()
    results = []
    for row in rows:
        r = dict(row)
        r["signals"] = json.loads(r["signals_json"])
        results.append(r)
    return results


# ── Meeting notes ──────────────────────────────────────────────────────────────

def upsert_meeting_note(path: str, title: str, excerpt: str, word_count: int, modified_at: float) -> None:
    conn = get_connection()
    conn.execute(
        "INSERT INTO meeting_notes (path, title, excerpt, word_count, modified_at, indexed_at) "
        "VALUES (?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(path) DO UPDATE SET "
        "title=excluded.title, excerpt=excluded.excerpt, "
        "word_count=excluded.word_count, modified_at=excluded.modified_at, "
        "indexed_at=excluded.indexed_at",
        (path, title, excerpt, word_count, modified_at, time.time()),
    )
    conn.commit()
    conn.close()


def get_recent_meeting_notes(limit: int = 10, since_hours: int = 48) -> list:
    since = time.time() - since_hours * 3600
    conn = get_connection()
    rows = conn.execute(
        "SELECT path, title, excerpt, word_count, modified_at FROM meeting_notes "
        "WHERE modified_at > ? ORDER BY modified_at DESC LIMIT ?",
        (since, limit),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


# ── Maintenance ────────────────────────────────────────────────────────────────

def clear_old_events(days: int = 7) -> None:
    cutoff = time.time() - (days * 86400)
    conn = get_connection()
    conn.execute("DELETE FROM file_events WHERE timestamp < ?", (cutoff,))
    conn.execute("DELETE FROM terminal_commands WHERE timestamp < ?", (cutoff,))
    conn.commit()
    conn.close()


def get_db_stats() -> dict:
    """Return row counts for all tables."""
    conn = get_connection()
    stats = {}
    for table in ("file_events", "git_commits", "terminal_commands", "context_summaries", "meeting_notes"):
        row = conn.execute(f"SELECT COUNT(*) as cnt FROM {table}").fetchone()
        stats[table] = row["cnt"] if row else 0
    conn.close()
    return stats


def get_signal_stats() -> dict:
    """Return rich signal stats for the dashboard stats bar."""
    conn = get_connection()
    now = time.time()

    file_count = conn.execute(
        "SELECT COUNT(*) FROM file_events WHERE timestamp > ?", (now - 3600,)
    ).fetchone()[0]

    total_commits = conn.execute("SELECT COUNT(*) FROM git_commits").fetchone()[0]

    cmd_count = conn.execute(
        "SELECT COUNT(*) FROM terminal_commands WHERE timestamp > ?", (now - 86400,)
    ).fetchone()[0]

    ctx_row = conn.execute(
        "SELECT created_at, token_estimate, generation_time_ms, provider "
        "FROM context_summaries ORDER BY created_at DESC LIMIT 1"
    ).fetchone()

    ctx_total = conn.execute("SELECT COUNT(*) FROM context_summaries").fetchone()[0]

    conn.close()

    return {
        "file_events_last_hour": file_count,
        "total_commits": total_commits,
        "commands_last_24h": cmd_count,
        "total_contexts_generated": ctx_total,
        "latest_context_at": ctx_row["created_at"] if ctx_row else None,
        "latest_token_estimate": ctx_row["token_estimate"] if ctx_row else 0,
        "latest_generation_ms": ctx_row["generation_time_ms"] if ctx_row else 0,
        "latest_provider": ctx_row["provider"] if ctx_row else "mock",
    }
