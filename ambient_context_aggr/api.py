"""FastAPI REST server exposing the aggregated context over HTTP."""

import os
import time

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import JSONResponse

from .database import (
    init_db,
    get_recent_file_events,
    get_recent_git_commits,
    get_recent_terminal_commands,
    get_context_summary_history,
    get_db_stats,
)
from .compressor import get_or_generate_context

app = FastAPI(
    title="Ambient Context Aggregator",
    description="Passive developer context tracking REST API",
    version="2.0.0",
)


@app.on_event("startup")
async def _startup():
    init_db()


@app.get("/health")
async def health():
    """Liveness probe with DB stats."""
    try:
        stats = get_db_stats()
    except Exception:
        stats = {}
    return {"status": "ok", "timestamp": time.time(), "db_stats": stats}


@app.get("/context")
async def get_context(
    force_refresh: bool = Query(False, description="Bypass the 5-minute cache"),
    mock: bool = Query(False, description="Skip LLM call, return template summary"),
):
    """Return the current compressed developer context."""
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    use_mock = mock or (not bool(anthropic_key) and not bool(openrouter_key))
    try:
        result = get_or_generate_context(force_refresh=force_refresh, use_mock=use_mock)
        return {
            "summary": result["summary"],
            "token_estimate": result["token_estimate"],
            "created_at": result["created_at"],
            "generation_time_ms": result.get("generation_time_ms", 0),
            "confidence": result.get("confidence", 0.0),
            "provider": result.get("provider", "mock"),
            "mock": use_mock,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/context/history")
async def get_context_history(limit: int = Query(10, ge=1, le=50)):
    """Return recent context summary history."""
    try:
        rows = get_context_summary_history(limit=limit)
        return {
            "history": [
                {
                    "summary": r["summary"],
                    "token_estimate": r["token_estimate"],
                    "created_at": r["created_at"],
                    "generation_time_ms": r.get("generation_time_ms", 0),
                    "provider": r.get("provider", "mock"),
                }
                for r in rows
            ],
            "count": len(rows),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/context/diff")
async def get_context_diff():
    """Return a summary of what changed between the two most recent context snapshots."""
    try:
        history = get_context_summary_history(limit=2)
        if len(history) < 2:
            return {"diff": "Not enough history to compare.", "snapshots": len(history)}
        newer, older = history[0], history[1]
        newer_lines = set(newer["summary"].splitlines())
        older_lines = set(older["summary"].splitlines())
        added = [l for l in newer_lines - older_lines if l.strip()]
        removed = [l for l in older_lines - newer_lines if l.strip()]
        return {
            "added_lines": added[:20],
            "removed_lines": removed[:20],
            "newer_created_at": newer["created_at"],
            "older_created_at": older["created_at"],
            "token_delta": newer["token_estimate"] - older["token_estimate"],
            "timestamp": time.time(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/signals")
async def get_signals():
    """Return the raw collected signals (files, commits, commands)."""
    try:
        return {
            "file_events": get_recent_file_events(limit=20),
            "git_commits": get_recent_git_commits(limit=10),
            "terminal_commands": get_recent_terminal_commands(limit=50),
            "fetched_at": time.time(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/signals/files")
async def get_file_signals(limit: int = Query(20, ge=1, le=100)):
    return {"file_events": get_recent_file_events(limit=limit), "fetched_at": time.time()}


@app.get("/signals/commits")
async def get_commit_signals(limit: int = Query(10, ge=1, le=50)):
    return {"git_commits": get_recent_git_commits(limit=limit), "fetched_at": time.time()}


@app.get("/signals/commands")
async def get_command_signals(limit: int = Query(50, ge=1, le=200)):
    return {"terminal_commands": get_recent_terminal_commands(limit=limit), "fetched_at": time.time()}


@app.get("/timeline")
async def get_timeline(hours: int = Query(8, ge=1, le=24)):
    """Return an hourly activity breakdown from stored signals."""
    try:
        import math
        from .database import get_recent_file_events, get_recent_terminal_commands

        now = time.time()
        buckets: dict = {}
        for h in range(hours):
            bucket_ts = now - h * 3600
            key = time.strftime("%H:00", time.localtime(bucket_ts))
            buckets[key] = {"hour": key, "file_events": 0, "commands": 0}

        events = get_recent_file_events(limit=500, since_seconds=hours * 3600)
        for e in events:
            key = time.strftime("%H:00", time.localtime(e["timestamp"]))
            if key in buckets:
                buckets[key]["file_events"] += 1

        cmds = get_recent_terminal_commands(limit=500)
        for c in cmds:
            key = time.strftime("%H:00", time.localtime(c["timestamp"]))
            if key in buckets:
                buckets[key]["commands"] += 1

        timeline = list(buckets.values())
        return {
            "timeline": timeline,
            "hours": hours,
            "fetched_at": time.time(),
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/meeting-notes")
@app.get("/notes")
async def get_meeting_notes(since_hours: int = Query(48, ge=1, le=168)):
    """Return recently modified meeting notes from the configured notes directory."""
    try:
        from .meeting_notes import scan_meeting_notes
        notes = scan_meeting_notes(since_hours=since_hours)
        return {"notes": notes, "count": len(notes), "fetched_at": time.time()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/focus")
async def get_focus():
    """Return the inferred developer focus (work type + confidence)."""
    try:
        from .compressor import build_signals_dict
        signals = build_signals_dict()
        from .timeline import compute_confidence_score
        confidence = compute_confidence_score(signals)
        return {"confidence": confidence, "signal_counts": {
            "files": len(signals.get("file_events", [])),
            "commits": len(signals.get("git_commits", [])),
            "commands": len(signals.get("terminal_commands", [])),
        }, "analysed_at": time.time()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/models")
async def list_models():
    """Return available model IDs for Claude and OpenRouter."""
    from .compressor import CLAUDE_MODELS, OPENROUTER_MODELS, _DEFAULT_CLAUDE_MODEL, _DEFAULT_OPENROUTER_MODEL
    return {
        "claude_models": CLAUDE_MODELS,
        "openrouter_models": OPENROUTER_MODELS,
        "defaults": {
            "claude": os.getenv("CLAUDE_MODEL", _DEFAULT_CLAUDE_MODEL),
            "openrouter": os.getenv("OPENROUTER_MODEL", _DEFAULT_OPENROUTER_MODEL),
        },
    }


@app.get("/stats")
async def get_stats():
    """Return database row counts and system statistics."""
    try:
        stats = get_db_stats()
        return {"db_stats": stats, "timestamp": time.time()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


def serve() -> None:
    """Start the uvicorn server. Called from the CLI."""
    import uvicorn

    host = os.getenv("API_HOST", "0.0.0.0")
    port = int(os.getenv("API_PORT", "8000"))
    uvicorn.run(app, host=host, port=port)
