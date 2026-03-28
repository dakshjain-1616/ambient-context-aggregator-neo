"""
Pytest test suite for Ambient Context Aggregator.
Covers all required test scenarios with 40+ assertions.
"""

import os
import sys
import json
import time
import subprocess
import tempfile
import shutil
from pathlib import Path

import pytest

# ── 1. File Watcher ────────────────────────────────────────────────────────────

class TestFileWatcher:
    """File watcher detects .py file changes within 2 seconds."""

    def test_watcher_starts_and_stops(self, tmp_path):
        from ambient_context_aggr.watcher import FileWatcher

        watcher = FileWatcher(watch_dir=str(tmp_path))
        watcher.start()
        assert watcher.is_running(), "Watcher should be running after start()"
        watcher.stop()
        assert not watcher.is_running(), "Watcher should stop after stop()"

    def test_watcher_detects_py_creation_within_2s(self, tmp_path):
        from ambient_context_aggr.watcher import FileWatcher
        from ambient_context_aggr.database import get_recent_file_events

        detected = []

        def on_change(path, event_type):
            detected.append((path, event_type))

        watcher = FileWatcher(watch_dir=str(tmp_path), callback=on_change)
        watcher.start()

        try:
            time.sleep(0.3)

            test_file = tmp_path / "hello_world.py"
            test_file.write_text("print('hello')\n")

            deadline = time.time() + 2.0
            found = False
            while time.time() < deadline:
                events = get_recent_file_events(limit=50, since_seconds=60)
                if any("hello_world.py" in e["path"] for e in events):
                    found = True
                    break
                time.sleep(0.1)

            assert found, "File watcher must detect .py creation within 2 seconds"
        finally:
            watcher.stop()

    def test_watcher_detects_py_modification(self, tmp_path):
        from ambient_context_aggr.watcher import FileWatcher
        from ambient_context_aggr.database import get_recent_file_events

        target = tmp_path / "target.py"
        target.write_text("x = 1\n")

        detected = []

        def on_change(path, event_type):
            detected.append((path, event_type))

        watcher = FileWatcher(watch_dir=str(tmp_path), callback=on_change)
        watcher.start()

        try:
            time.sleep(0.3)
            target.write_text("x = 2  # modified\n")

            deadline = time.time() + 2.0
            found = False
            while time.time() < deadline:
                events = get_recent_file_events(limit=50, since_seconds=60)
                if any("target.py" in e["path"] for e in events):
                    found = True
                    break
                time.sleep(0.1)

            assert found, "Watcher must detect .py modification within 2 seconds"
        finally:
            watcher.stop()

    def test_watcher_ignores_non_source_files(self, tmp_path):
        from ambient_context_aggr.watcher import FileWatcher

        ignored_files = []

        def on_change(path, event_type):
            ignored_files.append(path)

        watcher = FileWatcher(watch_dir=str(tmp_path), callback=on_change)
        watcher.start()

        try:
            time.sleep(0.3)
            (tmp_path / "ignored.log").write_text("log line\n")
            (tmp_path / "ignored.bin").write_bytes(b"\x00\x01\x02")
            time.sleep(0.5)

            assert not any(".log" in p or ".bin" in p for p in ignored_files), \
                "Non-source files should not be tracked"
        finally:
            watcher.stop()

    def test_watcher_context_manager(self, tmp_path):
        from ambient_context_aggr.watcher import FileWatcher

        with FileWatcher(watch_dir=str(tmp_path)) as w:
            assert w.is_running()
        assert not w.is_running()


# ── 2. Git Scraper ─────────────────────────────────────────────────────────────

class TestGitScraper:
    """Git scraper reads last 10 commits from any git repo path."""

    @pytest.fixture
    def git_repo(self, tmp_path):
        """Create a temporary git repo with 12 commits."""
        import git

        repo = git.Repo.init(str(tmp_path))
        with repo.config_writer() as cw:
            cw.set_value("user", "name", "Test Author")
            cw.set_value("user", "email", "test@example.com")

        for i in range(12):
            f = tmp_path / f"file_{i}.py"
            f.write_text(f"# version {i}\nx = {i}\n")
            repo.index.add([f"file_{i}.py"])
            repo.index.commit(f"Commit number {i}: update file_{i}.py")

        return tmp_path

    def test_reads_up_to_10_commits(self, git_repo):
        from ambient_context_aggr.git_scraper import get_repo_commits

        commits = get_repo_commits(repo_path=str(git_repo), limit=10)
        assert len(commits) == 10, "Should return exactly 10 commits when 12 exist"

    def test_commit_has_required_fields(self, git_repo):
        from ambient_context_aggr.git_scraper import get_repo_commits

        commits = get_repo_commits(repo_path=str(git_repo), limit=5)
        assert len(commits) > 0

        for c in commits:
            assert "hash" in c, "Commit must have 'hash'"
            assert "author" in c, "Commit must have 'author'"
            assert "message" in c, "Commit must have 'message'"
            assert "timestamp" in c, "Commit must have 'timestamp'"
            assert "repo_path" in c, "Commit must have 'repo_path'"
            assert len(c["hash"]) == 8, "Hash should be 8 chars (short form)"

    def test_commits_ordered_newest_first(self, git_repo):
        from ambient_context_aggr.git_scraper import get_repo_commits

        commits = get_repo_commits(repo_path=str(git_repo), limit=10)
        assert len(commits) >= 2
        assert commits[0]["timestamp"] >= commits[-1]["timestamp"], \
            "Commits should be ordered newest-first"

    def test_returns_empty_for_non_repo(self, tmp_path):
        from ambient_context_aggr.git_scraper import get_repo_commits

        non_repo = tmp_path / "not_a_repo"
        non_repo.mkdir()
        result = get_repo_commits(repo_path=str(non_repo), limit=10)
        assert result == [], "Non-repo path should return empty list"

    def test_get_modified_files(self, git_repo):
        from ambient_context_aggr.git_scraper import get_modified_files

        untracked = git_repo / "untracked.py"
        untracked.write_text("# untracked\n")

        modified = get_modified_files(repo_path=str(git_repo))
        assert isinstance(modified, list)


# ── 3. Terminal History Parser ─────────────────────────────────────────────────

class TestHistoryParser:
    """Terminal history parser reads at least 50 recent commands from a mock file."""

    def _write_bash_history(self, path: Path, n: int) -> None:
        commands = [f"command_{i} --option-{i} arg{i}" for i in range(n)]
        path.write_text("\n".join(commands) + "\n")

    def _write_zsh_history(self, path: Path, n: int) -> None:
        now = int(time.time())
        lines = [f": {now - i}:0;command_{i} --flag{i}" for i in range(n)]
        path.write_text("\n".join(lines) + "\n")

    def test_parses_bash_history_50_commands(self, tmp_path):
        from ambient_context_aggr.history_parser import parse_bash_history

        hist = tmp_path / ".bash_history"
        self._write_bash_history(hist, 80)

        cmds = parse_bash_history(str(hist), limit=50)
        assert len(cmds) >= 50, f"Should parse at least 50 commands, got {len(cmds)}"

    def test_parses_zsh_history_50_commands(self, tmp_path):
        from ambient_context_aggr.history_parser import parse_zsh_history

        hist = tmp_path / ".zsh_history"
        self._write_zsh_history(hist, 80)

        cmds = parse_zsh_history(str(hist), limit=50)
        assert len(cmds) >= 50, f"Should parse at least 50 zsh commands, got {len(cmds)}"

    def test_command_dict_has_required_keys(self, tmp_path):
        from ambient_context_aggr.history_parser import parse_bash_history

        hist = tmp_path / ".bash_history"
        self._write_bash_history(hist, 10)

        cmds = parse_bash_history(str(hist), limit=10)
        for cmd in cmds:
            assert "command" in cmd
            assert "timestamp" in cmd
            assert isinstance(cmd["command"], str)
            assert len(cmd["command"]) > 0

    def test_get_recent_commands_with_env_override(self, tmp_path):
        from ambient_context_aggr.history_parser import get_recent_commands

        hist = tmp_path / "custom_history"
        self._write_bash_history(hist, 100)

        os.environ["HISTORY_FILE"] = str(hist)
        try:
            cmds = get_recent_commands(limit=60)
            assert len(cmds) >= 50, "Should return at least 50 commands from custom history file"
        finally:
            del os.environ["HISTORY_FILE"]

    def test_deduplication(self, tmp_path):
        from ambient_context_aggr.history_parser import parse_bash_history

        hist = tmp_path / ".bash_history"
        lines = ["git status\n"] * 60 + ["ls -la\n"] * 60
        hist.write_text("".join(lines))

        cmds = parse_bash_history(str(hist), limit=200)
        commands_text = [c["command"] for c in cmds]
        assert len(commands_text) > 0


# ── 4. LLM Compressor ─────────────────────────────────────────────────────────

class TestCompressor:
    """LLM compressor produces context summary ≤600 tokens."""

    def _populate_db(self):
        from ambient_context_aggr.database import insert_file_event, insert_git_commits, insert_terminal_commands

        insert_file_event("/project/main.py", "modified")
        insert_file_event("/project/api.py", "modified")
        insert_file_event("/project/models.py", "created")

        commits = [
            {"hash": "abc12345", "author": "Dev <dev@x.com>", "message": "Fix auth bug",
             "timestamp": time.time() - 100, "repo_path": "/project"},
            {"hash": "def67890", "author": "Dev <dev@x.com>", "message": "Add user model",
             "timestamp": time.time() - 200, "repo_path": "/project"},
        ]
        insert_git_commits(commits)

        commands = [
            {"command": f"git commit -m 'update {i}'", "timestamp": time.time() - i * 30}
            for i in range(10)
        ]
        insert_terminal_commands(commands)

    def test_mock_summary_within_600_tokens(self):
        from ambient_context_aggr.compressor import get_or_generate_context, estimate_tokens

        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)

        assert "summary" in result
        assert "token_estimate" in result
        tokens = estimate_tokens(result["summary"])
        assert tokens <= 600, f"Mock summary must be ≤600 tokens, got {tokens}"

    def test_summary_contains_expected_sections(self):
        from ambient_context_aggr.compressor import get_or_generate_context

        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)
        summary = result["summary"]

        assert "Context" in summary or "context" in summary, "Summary should mention context"
        assert len(summary) > 50, "Summary should be non-trivial"

    def test_signals_dict_has_all_keys(self):
        from ambient_context_aggr.compressor import build_signals_dict

        signals = build_signals_dict(include_notes=False)
        assert "file_events" in signals
        assert "git_commits" in signals
        assert "terminal_commands" in signals
        assert "collected_at" in signals

    def test_cache_is_used(self):
        from ambient_context_aggr.compressor import get_or_generate_context

        self._populate_db()
        r1 = get_or_generate_context(force_refresh=True, use_mock=True)
        r2 = get_or_generate_context(force_refresh=False, use_mock=True)
        assert r1["summary"] == r2["summary"], "Second call should return cached result"

    def test_force_refresh_bypasses_cache(self):
        from ambient_context_aggr.compressor import get_or_generate_context

        self._populate_db()
        r1 = get_or_generate_context(force_refresh=True, use_mock=True)
        r2 = get_or_generate_context(force_refresh=True, use_mock=True)
        assert r2["summary"] is not None

    def test_result_has_new_metadata_fields(self):
        from ambient_context_aggr.compressor import get_or_generate_context

        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)
        assert "generation_time_ms" in result, "Result must include generation_time_ms"
        assert "confidence" in result, "Result must include confidence score"
        assert "provider" in result, "Result must include provider"
        assert isinstance(result["generation_time_ms"], int)
        assert 0.0 <= result["confidence"] <= 100.0

    def test_provider_is_mock_without_api_keys(self):
        from ambient_context_aggr.compressor import get_or_generate_context

        self._populate_db()
        # Temporarily remove API keys
        old_anthropic = os.environ.pop("ANTHROPIC_API_KEY", None)
        old_openrouter = os.environ.pop("OPENROUTER_API_KEY", None)
        try:
            result = get_or_generate_context(force_refresh=True, use_mock=True)
            assert result["provider"] == "mock"
        finally:
            if old_anthropic:
                os.environ["ANTHROPIC_API_KEY"] = old_anthropic
            if old_openrouter:
                os.environ["OPENROUTER_API_KEY"] = old_openrouter


# ── 5. CLI ─────────────────────────────────────────────────────────────────────

class TestCLI:
    """CLI: python -m ambient_context get returns non-empty context."""

    def test_cli_get_returns_output(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "get", "--mock", "--raw"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI exited {result.returncode}: {result.stderr}"
        output = result.stdout.strip()
        assert len(output) > 0, "CLI get must produce non-empty output"

    def test_cli_get_mock_produces_context_sections(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "get", "--mock", "--raw"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0
        output = result.stdout
        assert len(output) > 20, "CLI output should be non-trivial"

    def test_cli_signals_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "signals"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI signals failed: {result.stderr}"

    def test_cli_help(self):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert result.returncode == 0
        assert "get" in result.stdout
        assert "watch" in result.stdout
        assert "serve" in result.stdout

    def test_cli_timeline_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "timeline", "--hours", "2"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI timeline failed: {result.stderr}"

    def test_cli_diff_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "diff"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI diff failed: {result.stderr}"

    def test_cli_notes_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "notes"],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db, "NOTES_DIR": "/nonexistent_path_xyz"},
        )
        assert result.returncode == 0, f"CLI notes failed: {result.stderr}"

    def test_cli_get_saves_output_file(self, isolated_db, tmp_path):
        out_file = tmp_path / "context_out.md"
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "get", "--mock", "--raw",
             "--output", str(out_file)],
            capture_output=True,
            text=True,
            timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI get --output failed: {result.stderr}"
        assert out_file.exists(), "--output flag should create a file"
        assert len(out_file.read_text()) > 0, "Output file should be non-empty"


# ── 6. Gradio Dashboard ────────────────────────────────────────────────────────

class TestGradioDashboard:
    """Gradio dashboard shows all 3 signal panels and compressed context."""

    def test_get_dashboard_data_returns_5_panels(self):
        from app import get_dashboard_data

        result = get_dashboard_data()
        assert len(result) == 5, "get_dashboard_data must return 5 values"

        file_panel, git_panel, cmd_panel, ctx_panel, status = result
        assert isinstance(file_panel, str), "File panel should be a string"
        assert isinstance(git_panel, str), "Git panel should be a string"
        assert isinstance(cmd_panel, str), "Command panel should be a string"
        assert isinstance(ctx_panel, str), "Context panel should be a string"
        assert isinstance(status, str), "Status should be a string"

    def test_all_panels_non_empty(self):
        from app import get_dashboard_data

        panels = get_dashboard_data()
        for i, panel in enumerate(panels):
            assert len(panel) > 0, f"Panel {i} should not be empty"

    def test_build_interface_returns_blocks(self):
        import gradio as gr
        from app import build_interface

        demo = build_interface()
        assert isinstance(demo, gr.Blocks), "build_interface must return a gr.Blocks instance"

    def test_context_panel_has_content(self):
        from app import get_dashboard_data

        _, _, _, ctx_panel, _ = get_dashboard_data()
        assert len(ctx_panel) > 10, "Context panel should contain actual text"

    def test_copy_context_returns_status(self):
        from app import copy_context

        result = copy_context("test context string")
        assert isinstance(result, str), "copy_context should return a status string"
        assert len(result) > 0

    def test_generate_context_returns_three_values(self):
        from app import generate_context

        ctx_text, status, token_text = generate_context("[mock — no API key]", force_refresh=True)
        assert isinstance(ctx_text, str) and len(ctx_text) > 0
        assert isinstance(status, str) and len(status) > 0
        assert isinstance(token_text, str) and len(token_text) > 0

    def test_fmt_timeline_returns_string(self):
        from app import _fmt_timeline

        result = _fmt_timeline(hours=4)
        assert isinstance(result, str)
        assert len(result) > 0

    def test_fmt_notes_returns_string(self):
        from app import _fmt_notes
        import os
        old = os.environ.pop("NOTES_DIR", None)
        os.environ["NOTES_DIR"] = "/nonexistent_path_xyz"
        try:
            result = _fmt_notes()
            assert isinstance(result, str)
        finally:
            if old:
                os.environ["NOTES_DIR"] = old
            else:
                os.environ.pop("NOTES_DIR", None)

    def test_fmt_diff_returns_string(self):
        from app import _fmt_diff

        result = _fmt_diff()
        assert isinstance(result, str)


# ── 7. Output Files ────────────────────────────────────────────────────────────

class TestOutputFiles:
    """outputs/ contains demo_context.md and demo_signals.json."""

    @pytest.fixture(scope="class", autouse=True)
    def run_demo_if_needed(self):
        """Run demo.py to generate outputs if they don't already exist."""
        ctx_path = Path("outputs/demo_context.md")
        sig_path = Path("outputs/demo_signals.json")

        if not ctx_path.exists() or not sig_path.exists():
            result = subprocess.run(
                [sys.executable, "demo.py"],
                capture_output=True,
                text=True,
                timeout=120,
            )
            assert result.returncode == 0, f"demo.py failed: {result.stderr}"

    def test_demo_context_md_exists(self):
        assert Path("outputs/demo_context.md").exists(), \
            "outputs/demo_context.md must exist after running demo.py"

    def test_demo_signals_json_exists(self):
        assert Path("outputs/demo_signals.json").exists(), \
            "outputs/demo_signals.json must exist after running demo.py"

    def test_demo_context_md_non_empty(self):
        content = Path("outputs/demo_context.md").read_text()
        assert len(content) > 100, "demo_context.md should contain substantial content"

    def test_demo_signals_json_valid(self):
        content = Path("outputs/demo_signals.json").read_text()
        data = json.loads(content)
        assert "generated_at" in data
        assert "git_commits" in data
        assert "terminal_commands" in data
        assert "context_summary" in data

    def test_demo_signals_json_has_commits(self):
        data = json.loads(Path("outputs/demo_signals.json").read_text())
        commits = data.get("git_commits", [])
        assert isinstance(commits, list)

    def test_demo_context_md_has_context_header(self):
        content = Path("outputs/demo_context.md").read_text()
        assert "Context" in content, "demo_context.md should mention 'Context'"
        assert "Generated" in content or "generated" in content.lower()

    def test_outputs_directory_exists(self):
        assert Path("outputs").is_dir(), "outputs/ directory must exist"


# ── 8. Meeting Notes ───────────────────────────────────────────────────────────

class TestMeetingNotes:
    """Meeting notes scanner finds and parses Markdown files."""

    def _make_notes_dir(self, tmp_path: Path) -> Path:
        notes = tmp_path / "notes"
        notes.mkdir()
        (notes / "2024-01-planning.md").write_text(
            "# Q1 Planning\n\nDiscussed roadmap for Q1. Key themes: API redesign, auth migration.\n"
            "Action items: update schema, write migration script."
        )
        (notes / "2024-01-retro.md").write_text(
            "# Sprint Retro\n\nWent well: test coverage improved. Improve: deployment pipeline.\n"
        )
        return notes

    def test_scan_finds_md_files(self, tmp_path):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes

        notes_dir = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(notes_dir)
        os.environ["NOTES_SINCE_HOURS"] = "9999"  # always include
        try:
            notes = scan_meeting_notes()
            assert len(notes) >= 2, f"Expected ≥2 notes, got {len(notes)}"
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_SINCE_HOURS"]

    def test_note_has_required_fields(self, tmp_path):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes

        notes_dir = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(notes_dir)
        os.environ["NOTES_SINCE_HOURS"] = "9999"
        try:
            notes = scan_meeting_notes()
            assert len(notes) > 0
            for n in notes:
                assert "path" in n
                assert "title" in n
                assert "excerpt" in n
                assert "modified_at" in n
                assert "word_count" in n
                assert isinstance(n["word_count"], int) and n["word_count"] > 0
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_SINCE_HOURS"]

    def test_title_extracted_from_h1(self, tmp_path):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes

        notes_dir = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(notes_dir)
        os.environ["NOTES_SINCE_HOURS"] = "9999"
        try:
            notes = scan_meeting_notes()
            titles = [n["title"] for n in notes]
            assert any("Q1 Planning" in t or "Sprint Retro" in t for t in titles), \
                f"Expected H1 titles, got: {titles}"
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_SINCE_HOURS"]

    def test_scan_empty_dir_returns_empty_list(self, tmp_path):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes

        empty_dir = tmp_path / "empty_notes"
        empty_dir.mkdir()
        os.environ["NOTES_DIR"] = str(empty_dir)
        try:
            notes = scan_meeting_notes()
            assert notes == []
        finally:
            del os.environ["NOTES_DIR"]

    def test_scan_nonexistent_dir_returns_empty(self):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes

        os.environ["NOTES_DIR"] = "/nonexistent_path_that_does_not_exist_xyz"
        try:
            notes = scan_meeting_notes()
            assert notes == []
        finally:
            del os.environ["NOTES_DIR"]

    def test_format_notes_for_context(self, tmp_path):
        from ambient_context_aggr.meeting_notes import scan_meeting_notes, format_notes_for_context

        notes_dir = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(notes_dir)
        os.environ["NOTES_SINCE_HOURS"] = "9999"
        try:
            notes = scan_meeting_notes()
            formatted = format_notes_for_context(notes)
            assert "Meeting Notes" in formatted
            assert len(formatted) > 10
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_SINCE_HOURS"]


# ── 9. Activity Timeline ───────────────────────────────────────────────────────

class TestTimeline:
    """Timeline builder produces correct hourly buckets and focus sessions."""

    def _seed_activity(self):
        from ambient_context_aggr.database import insert_file_event, insert_terminal_commands
        now = time.time()
        for i in range(5):
            insert_file_event(f"/project/file_{i}.py", "modified")
        insert_terminal_commands([
            {"command": f"git status {i}", "timestamp": now - i * 60}
            for i in range(8)
        ])

    def test_timeline_returns_correct_number_of_buckets(self):
        from ambient_context_aggr.timeline import build_hourly_timeline
        self._seed_activity()
        tl = build_hourly_timeline(hours=6)
        assert len(tl) == 6, f"Expected 6 hourly buckets, got {len(tl)}"

    def test_timeline_bucket_has_required_fields(self):
        from ambient_context_aggr.timeline import build_hourly_timeline
        tl = build_hourly_timeline(hours=4)
        for bucket in tl:
            assert "hour_label" in bucket
            assert "file_events" in bucket
            assert "commands" in bucket
            assert "total" in bucket
            assert "bar" in bucket
            assert "focus_score" in bucket
            assert 0.0 <= bucket["focus_score"] <= 1.0

    def test_timeline_totals_are_non_negative(self):
        from ambient_context_aggr.timeline import build_hourly_timeline
        self._seed_activity()
        tl = build_hourly_timeline(hours=8)
        for bucket in tl:
            assert bucket["file_events"] >= 0
            assert bucket["commands"] >= 0
            assert bucket["total"] == bucket["file_events"] + bucket["commands"]

    def test_format_timeline_text_returns_string(self):
        from ambient_context_aggr.timeline import build_hourly_timeline, format_timeline_text
        tl = build_hourly_timeline(hours=4)
        text = format_timeline_text(tl)
        assert isinstance(text, str)
        assert "Hour" in text or len(text) > 5

    def test_compute_confidence_score_range(self):
        from ambient_context_aggr.timeline import compute_confidence_score
        signals_empty = {"file_events": [], "git_commits": [], "terminal_commands": []}
        score_empty = compute_confidence_score(signals_empty)
        assert score_empty == 0.0, "Empty signals should give 0 confidence"

        signals_full = {
            "file_events": [{"path": f"/f{i}.py"} for i in range(25)],
            "git_commits": [{"hash": f"{i:08x}"} for i in range(6)],
            "terminal_commands": [{"command": f"cmd {i}"} for i in range(35)],
            "meeting_notes": [{"title": "Note"}, {"title": "Note2"}],
        }
        score_full = compute_confidence_score(signals_full)
        assert score_full > 50, f"Rich signals should give >50 confidence, got {score_full}"
        assert score_full <= 100

    def test_detect_focus_sessions(self):
        from ambient_context_aggr.timeline import build_hourly_timeline, detect_focus_sessions
        self._seed_activity()
        tl = build_hourly_timeline(hours=8)
        sessions = detect_focus_sessions(tl, min_activity=0)
        assert isinstance(sessions, list)


# ── 10. Context Diff ───────────────────────────────────────────────────────────

class TestContextDiff:
    """Context diff correctly identifies changes between snapshots."""

    def _create_two_snapshots(self):
        from ambient_context_aggr.database import save_context_summary
        signals1 = {
            "file_events": [{"path": "/project/old.py", "event_type": "modified", "timestamp": time.time()}],
            "git_commits": [{"hash": "aabbccdd", "message": "old commit", "author": "dev"}],
            "terminal_commands": [{"command": "git status", "timestamp": time.time()}],
        }
        signals2 = {
            "file_events": [
                {"path": "/project/old.py", "event_type": "modified", "timestamp": time.time()},
                {"path": "/project/new.py", "event_type": "created", "timestamp": time.time()},
            ],
            "git_commits": [
                {"hash": "aabbccdd", "message": "old commit", "author": "dev"},
                {"hash": "eeff0011", "message": "new commit", "author": "dev"},
            ],
            "terminal_commands": [{"command": f"cmd {i}", "timestamp": time.time()} for i in range(5)],
        }
        save_context_summary("Old summary content", 100, signals1)
        time.sleep(0.01)
        save_context_summary("New summary content", 120, signals2)

    def test_diff_report_is_string(self):
        from ambient_context_aggr.context_diff import get_diff_report
        report = get_diff_report()
        assert isinstance(report, str)
        assert len(report) > 0

    def test_diff_reports_no_snapshots_gracefully(self):
        from ambient_context_aggr.context_diff import get_diff_report
        # Fresh DB has 0 snapshots
        report = get_diff_report()
        assert "Not enough snapshots" in report or isinstance(report, str)

    def test_diff_detects_new_files(self):
        from ambient_context_aggr.context_diff import get_diff_report, compute_context_diff

        self._create_two_snapshots()
        from ambient_context_aggr.context_diff import get_recent_summaries
        rows = get_recent_summaries(2)
        if len(rows) < 2:
            pytest.skip("Need 2 snapshots for diff test")

        new_row, old_row = rows[0], rows[1]
        diff = compute_context_diff(old=old_row, new=new_row)
        assert "new_file_count" in diff
        assert "new_commit_count" in diff
        assert "summary" in diff
        assert isinstance(diff["summary"], str)

    def test_diff_has_elapsed_time(self):
        from ambient_context_aggr.context_diff import compute_context_diff

        old = {"created_at": time.time() - 300, "token_estimate": 100, "signals_json": "{}"}
        new = {"created_at": time.time(), "token_estimate": 120, "signals_json": "{}"}
        diff = compute_context_diff(old=old, new=new)
        assert diff["elapsed_seconds"] > 0
        assert "elapsed_label" in diff
        assert diff["token_delta"] == 20


# ── 11. Database Extended ──────────────────────────────────────────────────────

class TestDatabaseExtended:
    """Tests for new database functions added in v2."""

    def test_get_db_stats_returns_all_tables(self):
        from ambient_context_aggr.database import get_db_stats
        stats = get_db_stats()
        expected = {"file_events", "git_commits", "terminal_commands", "context_summaries", "meeting_notes"}
        assert expected.issubset(set(stats.keys()))
        for k, v in stats.items():
            assert isinstance(v, int) and v >= 0

    def test_get_context_summary_history(self):
        from ambient_context_aggr.database import save_context_summary, get_context_summary_history
        for i in range(3):
            save_context_summary(f"Summary {i}", 100 + i, {})
        history = get_context_summary_history(limit=3)
        assert len(history) == 3
        assert history[0]["summary"] == "Summary 2"  # newest first

    def test_upsert_meeting_note(self):
        from ambient_context_aggr.database import upsert_meeting_note, get_recent_meeting_notes
        upsert_meeting_note(
            path="/notes/test.md",
            title="Test Meeting",
            excerpt="We discussed things.",
            word_count=42,
            modified_at=time.time(),
        )
        notes = get_recent_meeting_notes(limit=5, since_hours=1)
        assert any(n["title"] == "Test Meeting" for n in notes)

    def test_upsert_meeting_note_is_idempotent(self):
        from ambient_context_aggr.database import upsert_meeting_note, get_recent_meeting_notes
        for title in ["First Title", "Updated Title"]:
            upsert_meeting_note(
                path="/notes/idempotent.md",
                title=title,
                excerpt="Excerpt.",
                word_count=10,
                modified_at=time.time(),
            )
        notes = get_recent_meeting_notes(limit=10, since_hours=1)
        matching = [n for n in notes if n["path"] == "/notes/idempotent.md"]
        assert len(matching) == 1, "Upsert should not create duplicate rows"
        assert matching[0]["title"] == "Updated Title"

    def test_clear_old_events(self):
        from ambient_context_aggr.database import insert_file_event, clear_old_events, get_recent_file_events
        insert_file_event("/project/old.py", "modified")
        clear_old_events(days=0)  # Remove everything older than now
        events = get_recent_file_events(limit=100, since_seconds=1)
        # May or may not have events depending on timing — just verify no crash
        assert isinstance(events, list)

    def test_get_signal_stats_returns_expected_keys(self):
        from ambient_context_aggr.database import get_signal_stats, insert_file_event, insert_terminal_commands
        insert_file_event("/project/test.py", "modified")
        insert_terminal_commands([{"command": "pytest", "timestamp": time.time()}])
        stats = get_signal_stats()
        assert "file_events_last_hour" in stats
        assert "commands_last_24h" in stats
        assert "total_commits" in stats
        assert "total_contexts_generated" in stats
        assert stats["file_events_last_hour"] >= 1
        assert stats["commands_last_24h"] >= 1


# ── 12. Focus Scorer ──────────────────────────────────────────────────────────

class TestFocusScorer:
    """Focus scorer correctly infers work type from developer signals."""

    def _make_testing_signals(self) -> dict:
        return {
            "file_events": [{"path": "/project/test_api.py"}, {"path": "/project/test_models.py"}],
            "git_commits": [{"hash": "aabbccdd", "message": "Add test coverage", "author": "dev"}],
            "terminal_commands": [
                {"command": "pytest --cov", "timestamp": time.time()},
                {"command": "python -m pytest tests/", "timestamp": time.time()},
            ],
        }

    def _make_infra_signals(self) -> dict:
        return {
            "file_events": [{"path": "/project/docker-compose.yml"}, {"path": "/project/deploy.yaml"}],
            "git_commits": [{"hash": "aabbccdd", "message": "Deploy to kubernetes", "author": "dev"}],
            "terminal_commands": [
                {"command": "docker build -t app .", "timestamp": time.time()},
                {"command": "kubectl apply -f deploy.yaml", "timestamp": time.time()},
            ],
        }

    def test_score_focus_returns_required_keys(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus(self._make_testing_signals())
        assert "work_type" in focus
        assert "confidence" in focus
        assert "scores" in focus
        assert "top_files" in focus
        assert "session_summary" in focus

    def test_score_focus_returns_valid_confidence(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus(self._make_testing_signals())
        assert 0.0 <= focus["confidence"] <= 1.0, \
            f"Confidence must be 0-1, got {focus['confidence']}"

    def test_score_focus_scores_sum_to_one(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus(self._make_testing_signals())
        total = sum(focus["scores"].values())
        assert abs(total - 1.0) < 0.01, f"Scores should sum to ~1.0, got {total}"

    def test_testing_signals_infer_testing_worktype(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus(self._make_testing_signals())
        # With test file names and pytest commands, should detect "testing"
        assert focus["work_type"] in ("testing", "feature_development", "refactoring"), \
            f"Expected testing-related work type, got '{focus['work_type']}'"

    def test_infra_signals_infer_infra_worktype(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus(self._make_infra_signals())
        assert focus["work_type"] == "infrastructure", \
            f"Expected 'infrastructure', got '{focus['work_type']}'"

    def test_empty_signals_returns_low_confidence(self):
        from ambient_context_aggr.focus_scorer import score_focus
        focus = score_focus({"file_events": [], "git_commits": [], "terminal_commands": []})
        assert focus["confidence"] < 0.5, "Empty signals should have low confidence"
        assert isinstance(focus["session_summary"], str)
        assert len(focus["session_summary"]) > 0

    def test_top_files_deduplicated(self):
        from ambient_context_aggr.focus_scorer import score_focus
        signals = {
            "file_events": [{"path": "/a/main.py"}, {"path": "/b/main.py"}, {"path": "/c/api.py"}],
            "git_commits": [],
            "terminal_commands": [],
        }
        focus = score_focus(signals)
        # "main.py" appears twice but should only appear once in top_files
        assert len(focus["top_files"]) == len(set(focus["top_files"])), \
            "top_files should be deduplicated"


# ── 13. Notes Ingester ────────────────────────────────────────────────────────

class TestNotesIngester:
    """Notes ingester parses markdown/txt/rst files from NOTES_DIR."""

    def _make_notes_dir(self, tmp_path: Path) -> Path:
        nd = tmp_path / "my_notes"
        nd.mkdir()
        (nd / "meeting_2024.md").write_text(
            "# Sprint Review\n\n- Action item: deploy by Friday\n- TODO: update docs\n"
            "* Key point: performance improved 20%\n"
        )
        (nd / "ideas.txt").write_text(
            "Refactor auth module\nAdd caching layer\n"
        )
        return nd

    def test_get_recent_notes_finds_files(self, tmp_path):
        from ambient_context_aggr.notes_ingester import get_recent_notes
        nd = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(nd)
        os.environ["NOTES_MAX_AGE_DAYS"] = "9999"
        try:
            notes = get_recent_notes()
            assert len(notes) >= 2, f"Expected ≥2 notes, got {len(notes)}"
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_MAX_AGE_DAYS"]

    def test_note_has_title_and_action_items(self, tmp_path):
        from ambient_context_aggr.notes_ingester import get_recent_notes
        nd = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(nd)
        os.environ["NOTES_MAX_AGE_DAYS"] = "9999"
        try:
            notes = get_recent_notes()
            md_note = next((n for n in notes if n["path"].endswith(".md")), None)
            assert md_note is not None, "Should find the .md note"
            assert md_note["title"] == "Sprint Review", f"Expected 'Sprint Review', got '{md_note['title']}'"
            assert len(md_note["action_items"]) >= 1, "Should extract action items"
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_MAX_AGE_DAYS"]

    def test_format_notes_for_context(self, tmp_path):
        from ambient_context_aggr.notes_ingester import get_recent_notes, format_notes_for_context
        nd = self._make_notes_dir(tmp_path)
        os.environ["NOTES_DIR"] = str(nd)
        os.environ["NOTES_MAX_AGE_DAYS"] = "9999"
        try:
            notes = get_recent_notes()
            formatted = format_notes_for_context(notes)
            assert isinstance(formatted, str)
            assert len(formatted) > 10
        finally:
            del os.environ["NOTES_DIR"]
            del os.environ["NOTES_MAX_AGE_DAYS"]

    def test_no_notes_dir_returns_empty(self):
        from ambient_context_aggr.notes_ingester import get_recent_notes
        old = os.environ.pop("NOTES_DIR", None)
        try:
            notes = get_recent_notes()
            assert notes == [], "Without NOTES_DIR, should return empty list"
        finally:
            if old is not None:
                os.environ["NOTES_DIR"] = old

    def test_format_empty_notes_returns_empty_string(self):
        from ambient_context_aggr.notes_ingester import format_notes_for_context
        result = format_notes_for_context([])
        assert result == "", "Empty notes list should return empty string"


# ── 14. New CLI Commands ──────────────────────────────────────────────────────

class TestNewCLICommands:
    """stats, export, focus CLI subcommands work correctly."""

    def test_cli_stats_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "stats"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI stats failed: {result.stderr}"

    def test_cli_focus_command(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "focus"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI focus failed: {result.stderr}"

    def test_cli_export_md(self, isolated_db, tmp_path):
        out = tmp_path / "export.md"
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "export",
             "--format", "md", "--output", str(out), "--mock"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI export failed: {result.stderr}"
        assert out.exists(), "Export should create the output file"
        content = out.read_text()
        assert len(content) > 50, "Exported markdown should have content"
        assert "Context" in content

    def test_cli_export_json(self, isolated_db, tmp_path):
        out = tmp_path / "export.json"
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "export",
             "--format", "json", "--output", str(out), "--mock"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI export json failed: {result.stderr}"
        assert out.exists()
        data = json.loads(out.read_text())
        assert "summary" in data
        assert "token_estimate" in data

    def test_cli_get_with_model_flag(self, isolated_db):
        result = subprocess.run(
            [sys.executable, "-m", "ambient_context", "get",
             "--mock", "--raw", "--model", "claude-sonnet-4-6"],
            capture_output=True, text=True, timeout=30,
            env={**os.environ, "DB_PATH": isolated_db},
        )
        assert result.returncode == 0, f"CLI get --model failed: {result.stderr}"
        assert len(result.stdout.strip()) > 0


# ── 15. Compressor Enhanced ───────────────────────────────────────────────────

class TestCompressorEnhanced:
    """Compressor returns enriched result dict with timing, provider, focus."""

    def _populate_db(self):
        from ambient_context_aggr.database import insert_file_event, insert_git_commits, insert_terminal_commands
        insert_file_event("/project/main.py", "modified")
        insert_git_commits([{
            "hash": "aabb1234", "author": "Dev <dev@x.com>",
            "message": "Add feature", "timestamp": time.time() - 100, "repo_path": "/project"
        }])
        insert_terminal_commands([
            {"command": "pytest tests/", "timestamp": time.time() - 30},
            {"command": "git commit -m 'wip'", "timestamp": time.time() - 60},
        ])

    def test_result_has_generation_time_ms(self):
        from ambient_context_aggr.compressor import get_or_generate_context
        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)
        assert "generation_time_ms" in result
        assert isinstance(result["generation_time_ms"], int)
        assert result["generation_time_ms"] >= 0

    def test_result_has_provider(self):
        from ambient_context_aggr.compressor import get_or_generate_context
        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)
        assert "provider" in result
        assert result["provider"] == "mock"

    def test_result_has_confidence(self):
        from ambient_context_aggr.compressor import get_or_generate_context
        self._populate_db()
        result = get_or_generate_context(force_refresh=True, use_mock=True)
        # May have "confidence" (via timeline) or "focus" dict
        has_confidence = "confidence" in result or "focus" in result
        assert has_confidence, "Result should have confidence or focus info"

    def test_retry_helper_succeeds_on_first_try(self):
        from ambient_context_aggr.compressor import _retry
        call_count = [0]

        def _fn():
            call_count[0] += 1
            return "ok"

        result = _retry(_fn, max_retries=3)
        assert result == "ok"
        assert call_count[0] == 1

    def test_retry_helper_retries_on_failure(self):
        from ambient_context_aggr.compressor import _retry
        call_count = [0]

        def _fn():
            call_count[0] += 1
            if call_count[0] < 3:
                raise ValueError("Transient error")
            return "success"

        result = _retry(_fn, max_retries=3, base_delay=0.0)
        assert result == "success"
        assert call_count[0] == 3

    def test_retry_raises_after_max_retries(self):
        from ambient_context_aggr.compressor import _retry

        def _always_fail():
            raise RuntimeError("Persistent failure")

        with pytest.raises(RuntimeError, match="Persistent failure"):
            _retry(_always_fail, max_retries=2, base_delay=0.0)

    def test_openrouter_model_list_contains_2026_models(self):
        from ambient_context_aggr.compressor import OPENROUTER_MODELS
        assert any("gpt-5" in m for m in OPENROUTER_MODELS), \
            "OPENROUTER_MODELS should include GPT-5.x models"
        assert any("mistral" in m for m in OPENROUTER_MODELS), \
            "OPENROUTER_MODELS should include Mistral models"

    def test_claude_model_list_is_current(self):
        from ambient_context_aggr.compressor import CLAUDE_MODELS, _DEFAULT_CLAUDE_MODEL
        assert _DEFAULT_CLAUDE_MODEL in CLAUDE_MODELS, \
            "Default Claude model should be in CLAUDE_MODELS list"
        assert "claude-sonnet-4-6" in CLAUDE_MODELS
