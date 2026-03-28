#!/usr/bin/env python3
"""03_custom_config.py — Configure behaviour via environment variables.

Shows how every major behaviour can be tuned through env vars: database
path, LLM provider, cache TTL, token budget, history limits, and notes
directory. All config is read at import or call time, so os.environ
assignments before the first import take effect immediately.
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import tempfile
import time

# ── Custom config via env vars (must be set before first import of the module) ──

tmpdir = tempfile.mkdtemp()

# Database location
os.environ["DB_PATH"] = os.path.join(tmpdir, "custom.db")

# LLM settings (swap provider / model without changing code)
os.environ["CLAUDE_MODEL"] = "claude-haiku-4-5-20251001"      # cheapest Claude
os.environ["CONTEXT_MAX_TOKENS"] = "400"                       # smaller summaries
os.environ["CONTEXT_CACHE_TTL"] = "60"                         # 1-minute cache
os.environ["LLM_MAX_RETRIES"] = "2"                            # fewer retries

# Signal collection limits
os.environ["MAX_COMMITS"] = "5"
os.environ["MAX_HISTORY_LINES"] = "20"
os.environ["NOTES_SINCE_HOURS"] = "24"

# ── Demo ────────────────────────────────────────────────────────────────────────

from ambient_context_aggr.database import init_db, insert_file_event, insert_terminal_commands
from ambient_context_aggr.compressor import (
    CACHE_TTL, MAX_RETRIES, _DEFAULT_CLAUDE_MODEL,
    build_signals_dict, get_or_generate_context,
)

init_db()

print("=== Active Configuration ===")
print(f"  DB_PATH             : {os.environ['DB_PATH']}")
print(f"  CLAUDE_MODEL        : {os.getenv('CLAUDE_MODEL', _DEFAULT_CLAUDE_MODEL)}")
print(f"  CONTEXT_MAX_TOKENS  : {os.getenv('CONTEXT_MAX_TOKENS', '600')}")
print(f"  CONTEXT_CACHE_TTL   : {CACHE_TTL}s")
print(f"  LLM_MAX_RETRIES     : {MAX_RETRIES}")
print(f"  MAX_COMMITS         : {os.getenv('MAX_COMMITS', '10')}")
print()

# Populate some signals
insert_file_event("/app/config.py", "modified")
insert_terminal_commands([
    {"command": "docker build -t myapp .", "timestamp": time.time()},
    {"command": "kubectl apply -f deploy.yaml", "timestamp": time.time()},
])

# Build signals dict (respects MAX_COMMITS, MAX_HISTORY_LINES from env)
signals = build_signals_dict(include_notes=False)
print(f"Signals collected:")
print(f"  file_events       : {len(signals['file_events'])}")
print(f"  git_commits       : {len(signals['git_commits'])}")
print(f"  terminal_commands : {len(signals['terminal_commands'])}")
print()

# Generate context (mock — no API key set)
result = get_or_generate_context(force_refresh=True, use_mock=True)
print(f"Context generated:")
print(f"  provider     : {result['provider']}")
print(f"  tokens       : ~{result['token_estimate']}")
print(f"  generated_ms : {result['generation_time_ms']}ms")
print(f"  confidence   : {result['confidence']}/100")

# Demonstrate cache: second call within TTL returns cached result
result2 = get_or_generate_context(force_refresh=False, use_mock=True)
print(f"\nSecond call (from cache):")
print(f"  provider: {result2['provider']}")

# Cleanup
import shutil
shutil.rmtree(tmpdir, ignore_errors=True)
