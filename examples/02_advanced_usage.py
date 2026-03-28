#!/usr/bin/env python3
"""02_advanced_usage.py — Advanced usage: signals inspection, timeline, focus analysis.

Demonstrates how to query individual signal streams, inspect the hourly
activity timeline, and run the focus scorer — all without an LLM call.
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import tempfile
from ambient_context_aggr.database import (
    init_db,
    insert_file_event,
    insert_git_commits,
    insert_terminal_commands,
    get_recent_file_events,
    get_recent_git_commits,
    get_recent_terminal_commands,
    get_db_stats,
)
from ambient_context_aggr.timeline import (
    build_hourly_timeline,
    format_timeline_text,
    compute_confidence_score,
)
from ambient_context_aggr.focus_scorer import score_focus

with tempfile.TemporaryDirectory() as tmp:
    os.environ["DB_PATH"] = os.path.join(tmp, "example.db")
    init_db()

    now = time.time()

    # Insert richer signal data
    insert_file_event("/project/src/auth.py", "modified")
    insert_file_event("/project/tests/test_auth.py", "modified")
    insert_file_event("/project/src/models.py", "created")
    insert_git_commits([
        {"hash": "abc12345", "author": "dev@example.com", "message": "fix: auth token expiry bug",
         "timestamp": now - 300, "repo_path": "/project"},
        {"hash": "def67890", "author": "dev@example.com", "message": "test: add auth test coverage",
         "timestamp": now - 600, "repo_path": "/project"},
    ])
    insert_terminal_commands([
        {"command": "pytest tests/test_auth.py -v", "timestamp": now - 100},
        {"command": "git diff HEAD~1", "timestamp": now - 200},
        {"command": "python -m pdb src/auth.py", "timestamp": now - 400},
    ])

    # --- Query signals ---
    print("=== Recent File Events ===")
    for e in get_recent_file_events(limit=5):
        print(f"  {e['event_type']:10s}  {e['path']}")

    print("\n=== Recent Commits ===")
    for c in get_recent_git_commits(limit=5):
        print(f"  [{c['hash']}] {c['message']}")

    # --- Timeline ---
    print("\n=== Activity Timeline (last 2h) ===")
    timeline = build_hourly_timeline(hours=2)
    print(format_timeline_text(timeline))

    # --- Confidence score ---
    signals = {
        "file_events": get_recent_file_events(),
        "git_commits": get_recent_git_commits(),
        "terminal_commands": get_recent_terminal_commands(),
        "meeting_notes": [],
    }
    conf = compute_confidence_score(signals)
    print(f"\nConfidence score: {conf}/100")

    # --- Focus analysis ---
    focus = score_focus(signals)
    print(f"\n=== Focus Analysis ===")
    print(f"  Work type  : {focus['work_type']}")
    print(f"  Confidence : {focus['confidence']:.0%}")
    print(f"  Summary    : {focus['session_summary']}")

    # --- DB stats ---
    print(f"\n=== Database Stats ===")
    for table, count in get_db_stats().items():
        print(f"  {table:30s} {count} rows")
