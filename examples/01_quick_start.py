#!/usr/bin/env python3
"""01_quick_start.py — Minimal working example of Ambient Context Aggregator.

Initialises the database, inserts a sample signal, and generates a mock
context summary. No API key required.
"""
import sys, os; sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import tempfile
from ambient_context_aggr.database import init_db, insert_file_event, insert_terminal_commands
from ambient_context_aggr.compressor import get_or_generate_context

# Use a temporary database so this example leaves no side-effects
with tempfile.TemporaryDirectory() as tmp:
    os.environ["DB_PATH"] = os.path.join(tmp, "example.db")

    # 1. Initialise the SQLite database
    init_db()

    # 2. Record some developer signals
    insert_file_event("/home/dev/project/api.py", "modified")
    insert_file_event("/home/dev/project/models.py", "created")
    insert_terminal_commands([
        {"command": "pytest tests/", "timestamp": __import__("time").time()},
        {"command": "git commit -m 'add user endpoint'", "timestamp": __import__("time").time()},
    ])

    # 3. Generate a context summary (mock mode — no API key needed)
    result = get_or_generate_context(force_refresh=True, use_mock=True)

    print(f"Provider : {result['provider']}")
    print(f"Tokens   : ~{result['token_estimate']}")
    print(f"Confidence: {result['confidence']}/100")
    print()
    print(result["summary"])
