"""Shared pytest fixtures for Ambient Context Aggregator tests."""

import os
import sys
import tempfile

import pytest

# Ensure project root is on the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(autouse=True)
def isolated_db(tmp_path):
    """Give every test its own fresh SQLite database."""
    db_path = str(tmp_path / "test_context.db")
    os.environ["DB_PATH"] = db_path

    from ambient_context_aggr.database import init_db
    init_db()

    yield db_path

    # Cleanup is handled by tmp_path fixture
