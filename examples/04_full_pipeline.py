#!/usr/bin/env python3
"""04_full_pipeline.py — End-to-end pipeline: watch → collect → compress → diff → export.

Demonstrates the complete Ambient Context Aggregator workflow:
  1. Start the file watcher (background thread)
  2. Simulate developer signals (file changes, git commits, shell commands)
  3. Generate a compressed context summary
  4. Generate a second summary and compute the diff
  5. Export the final context to a markdown file

Runs entirely in mock mode — no API key required.
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import time
import tempfile
import json
from pathlib import Path

# ── Setup isolated environment ──────────────────────────────────────────────────

tmpdir = tempfile.mkdtemp()
os.environ["DB_PATH"] = os.path.join(tmpdir, "pipeline.db")
os.environ["WATCH_DIR"] = tmpdir

from ambient_context_aggr.database import (
    init_db,
    insert_file_event,
    insert_git_commits,
    insert_terminal_commands,
)
from ambient_context_aggr.watcher import FileWatcher
from ambient_context_aggr.compressor import get_or_generate_context, build_signals_dict
from ambient_context_aggr.context_diff import get_diff_report, compute_context_diff, get_recent_summaries
from ambient_context_aggr.timeline import build_hourly_timeline, format_timeline_text, compute_confidence_score
from ambient_context_aggr.focus_scorer import score_focus

print("=" * 60)
print("  Ambient Context Aggregator — Full Pipeline Demo")
print("=" * 60)

# ── Step 1: Initialise and start file watcher ────────────────────────────────────

init_db()
print("\n[1/5] Starting file watcher...")
watcher = FileWatcher(watch_dir=tmpdir)
watcher.start()
print(f"      Watching: {tmpdir}")

# Trigger a real filesystem event so the watcher has something to detect
watched_file = Path(tmpdir) / "feature.py"
watched_file.write_text("# new feature\n")
time.sleep(0.8)  # let watchdog pick it up
print(f"      Detected events: {len(watcher.handler.get_recent_changes())}")
watcher.stop()

# ── Step 2: Inject richer developer signals ──────────────────────────────────────

print("\n[2/5] Injecting developer signals...")
now = time.time()

insert_file_event("/project/src/auth.py", "modified")
insert_file_event("/project/src/api.py", "modified")
insert_file_event("/project/tests/test_auth.py", "created")

insert_git_commits([
    {"hash": "aaa11111", "author": "alice <alice@dev.io>",
     "message": "feat: add JWT refresh endpoint", "timestamp": now - 900, "repo_path": "/project"},
    {"hash": "bbb22222", "author": "alice <alice@dev.io>",
     "message": "test: coverage for auth module", "timestamp": now - 600, "repo_path": "/project"},
    {"hash": "ccc33333", "author": "alice <alice@dev.io>",
     "message": "fix: token expiry off-by-one", "timestamp": now - 300, "repo_path": "/project"},
])

insert_terminal_commands([
    {"command": "pytest tests/test_auth.py -v --cov=src", "timestamp": now - 250},
    {"command": "git diff HEAD~1 src/auth.py", "timestamp": now - 200},
    {"command": "python -c 'import jwt; print(jwt.__version__)'", "timestamp": now - 150},
    {"command": "pip install PyJWT==2.8.0", "timestamp": now - 100},
])

print("      File events  : 3 inserted")
print("      Git commits  : 3 inserted")
print("      Commands     : 4 inserted")

# ── Step 3: Generate first context summary ───────────────────────────────────────

print("\n[3/5] Generating first context summary (mock)...")
result1 = get_or_generate_context(force_refresh=True, use_mock=True)
print(f"      Provider  : {result1['provider']}")
print(f"      Tokens    : ~{result1['token_estimate']}")
print(f"      Confidence: {result1['confidence']}/100")

# ── Step 4: Add more signals and generate diff ───────────────────────────────────

print("\n[4/5] Adding new signals and computing diff...")
time.sleep(0.1)  # ensure created_at differs

insert_file_event("/project/src/permissions.py", "created")
insert_git_commits([
    {"hash": "ddd44444", "author": "alice <alice@dev.io>",
     "message": "feat: role-based access control", "timestamp": now - 50, "repo_path": "/project"},
])
insert_terminal_commands([
    {"command": "pytest tests/ --cov=src --cov-report=html", "timestamp": now - 30},
])

result2 = get_or_generate_context(force_refresh=True, use_mock=True)

rows = get_recent_summaries(2)
if len(rows) >= 2:
    diff = compute_context_diff(old=rows[1], new=rows[0])
    print(f"      Token delta      : {diff['token_delta']:+d}")
    print(f"      New file events  : {diff['new_file_count']}")
    print(f"      New commits      : {diff['new_commit_count']}")
    print(f"      What changed     : {diff['summary']}")
else:
    print("      (need 2 snapshots for diff)")

# ── Step 5: Timeline, focus analysis, and export ─────────────────────────────────

print("\n[5/5] Timeline, focus analysis, and export...")

signals = build_signals_dict(include_notes=False)

# Focus analysis
focus = score_focus(signals)
print(f"      Work type   : {focus['work_type'].replace('_', ' ').title()}")
print(f"      Confidence  : {focus['confidence']:.0%}")
print(f"      Top files   : {', '.join(focus['top_files'][:3])}")

# Timeline
timeline = build_hourly_timeline(hours=2)
active_hours = [h for h in timeline if h["total"] > 0]
print(f"      Active hours: {len(active_hours)}/2")

# Export to markdown
export_path = Path(tmpdir) / "context_export.md"
export_path.write_text(
    f"# Ambient Context Export\n\n"
    f"**Provider:** {result2['provider']}\n"
    f"**Tokens:** ~{result2['token_estimate']}\n"
    f"**Focus:** {focus['work_type']} ({focus['confidence']:.0%})\n\n"
    f"---\n\n"
    f"{result2['summary']}\n"
)
print(f"      Exported to : {export_path}")

# Export signals as JSON
signals_path = Path(tmpdir) / "signals.json"
signals_path.write_text(json.dumps({
    k: v for k, v in signals.items() if k != "collected_at"
}, indent=2, default=str))
print(f"      Signals JSON: {signals_path}")

print("\n" + "=" * 60)
print("  Pipeline complete.")
print("=" * 60)

# Cleanup
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
