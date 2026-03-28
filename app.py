"""Gradio dashboard — tabbed live context snapshot with stats, history, and meeting notes."""

import os
import time
from pathlib import Path
from datetime import datetime

import gradio as gr
from dotenv import load_dotenv

load_dotenv()

from ambient_context_aggr.database import (
    init_db,
    get_recent_file_events,
    get_recent_git_commits,
    get_recent_terminal_commands,
    get_context_summary_history,
    get_db_stats,
)
from ambient_context_aggr.compressor import get_or_generate_context

# ── Model options ──────────────────────────────────────────────────────────────

ANTHROPIC_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
]

OPENROUTER_MODELS = [
    "mistralai/mistral-small-2603",
    "openai/gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "openai/gpt-5.4",
    "x-ai/grok-4.20-beta",
    "x-ai/grok-4.20-multi-agent-beta",
    "xiaomi/mimo-v2-pro",
    "minimax/minimax-m2.7",
    "nvidia/nemotron-3-super-120b-a12b:free",
]

ALL_MODELS = ["[mock — no API key]"] + ANTHROPIC_MODELS + OPENROUTER_MODELS

DEFAULT_MODEL = os.getenv("CLAUDE_MODEL", "claude-sonnet-4-6")

# Session-level generation counter (local single-user tool)
_generation_count = 0


# ── Formatters ─────────────────────────────────────────────────────────────────

def _fmt_files(events: list) -> str:
    """Format file-change events into a monospace table string."""
    if not events:
        return "No file changes recorded in the last hour.\nRun `python -m ambient_context watch` to start tracking."
    lines = []
    for e in events[:15]:
        ts = datetime.fromtimestamp(e["timestamp"]).strftime("%H:%M:%S")
        name = Path(e["path"]).name
        lines.append(f"[{ts}]  {e['event_type']:10s}  {name}")
    return "\n".join(lines)


def _fmt_commits(commits: list) -> str:
    """Format recent git commits into a monospace summary string."""
    if not commits:
        return "No git commits found.\nSet GIT_REPO_PATH to point at your repository."
    lines = []
    for c in commits[:10]:
        ts = datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d")
        author = c["author"].split("<")[0].strip()[:14]
        lines.append(f"{c['hash']}  {ts}  {author:<14s}  {c['message'][:50]}")
    return "\n".join(lines)


def _fmt_commands(commands: list) -> str:
    """Format recent terminal commands into a monospace list string."""
    if not commands:
        return "No terminal commands found.\nShell history will be read automatically on next refresh."
    lines = []
    for c in commands[:20]:
        ts = datetime.fromtimestamp(c["timestamp"]).strftime("%H:%M:%S")
        lines.append(f"[{ts}]  {c['command'][:75]}")
    return "\n".join(lines)


def _fmt_timeline(hours: int = 8) -> str:
    """Render the hourly activity timeline for the given look-back window."""
    try:
        from ambient_context_aggr.timeline import build_hourly_timeline, format_timeline_text
        tl = build_hourly_timeline(hours=hours)
        return format_timeline_text(tl)
    except Exception as exc:
        return f"Timeline unavailable: {exc}"


def _fmt_notes() -> str:
    """Scan and format recent meeting notes from NOTES_DIR."""
    try:
        from ambient_context_aggr.meeting_notes import scan_meeting_notes, format_notes_for_context
        notes = scan_meeting_notes()
        if not notes:
            return (
                "No recent meeting notes found.\n"
                "Set NOTES_DIR to your notes folder (e.g. ~/notes).\n"
                "The scanner looks for .md files modified in the last 48h."
            )
        return format_notes_for_context(notes)
    except Exception as exc:
        return f"Notes unavailable: {exc}"


def _fmt_diff() -> str:
    """Return a human-readable diff between the last two context snapshots."""
    try:
        from ambient_context_aggr.context_diff import get_diff_report
        return get_diff_report()
    except Exception as exc:
        return f"Diff unavailable: {exc}"


def _fmt_history() -> str:
    """Format the last 5 context snapshots with timestamps and provider info."""
    rows = get_context_summary_history(limit=5)
    if not rows:
        return "No context history yet. Generate a context first."
    parts = []
    for i, r in enumerate(rows):
        ts = datetime.fromtimestamp(r["created_at"]).strftime("%Y-%m-%d %H:%M:%S")
        provider = r.get("provider", "mock")
        tokens = r.get("token_estimate", 0)
        gen_ms = r.get("generation_time_ms", 0)
        parts.append(
            f"─── Snapshot {i+1}  [{ts}]  {provider}  ~{tokens} tokens  {gen_ms}ms ───\n"
            + r["summary"][:400]
            + ("…" if len(r["summary"]) > 400 else "")
        )
    return "\n\n".join(parts)


def _fmt_stats() -> str:
    """Return a formatted string of SQLite row counts per table."""
    try:
        stats = get_db_stats()
        lines = ["Database Statistics:", ""]
        for table, count in stats.items():
            lines.append(f"  {table:<25s}  {count:>6d} rows")
        return "\n".join(lines)
    except Exception as exc:
        return f"Stats unavailable: {exc}"


def _compute_status(ctx: dict, use_mock: bool) -> str:
    """Build a one-line status string from a context result dict."""
    provider = ctx.get("provider", "mock")
    tokens = ctx.get("token_estimate", 0)
    conf = ctx.get("confidence", 0.0)
    gen_ms = ctx.get("generation_time_ms", 0)
    ts = datetime.now().strftime("%H:%M:%S")
    return (
        f"~{tokens} tokens  |  confidence {conf}/100  |  "
        f"{provider}  |  {gen_ms}ms  |  updated {ts}"
    )


# ── Data fetchers ──────────────────────────────────────────────────────────────

def get_dashboard_data() -> tuple:
    """Fetch all panels. Returns (files, commits, commands, context, status)."""
    try:
        init_db()
        file_events = get_recent_file_events(limit=15, since_seconds=3600)
        git_commits = get_recent_git_commits(limit=10)
        terminal_commands = get_recent_terminal_commands(limit=20)

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        use_mock = not bool(anthropic_key) and not bool(openrouter_key)
        ctx = get_or_generate_context(use_mock=use_mock)

        status = _compute_status(ctx, use_mock)

        return (
            _fmt_files(file_events),
            _fmt_commits(git_commits),
            _fmt_commands(terminal_commands),
            ctx["summary"],
            status,
        )
    except Exception as exc:
        err = f"Error: {exc}"
        return err, err, err, err, "Error — check terminal for details"


def refresh_signals() -> tuple:
    """Refresh signals (no LLM call), return (files, commits, commands, status)."""
    try:
        init_db()
        file_events = get_recent_file_events(limit=15, since_seconds=3600)
        git_commits = get_recent_git_commits(limit=10)
        terminal_commands = get_recent_terminal_commands(limit=20)
        ts = datetime.now().strftime("%H:%M:%S")
        return (
            _fmt_files(file_events),
            _fmt_commits(git_commits),
            _fmt_commands(terminal_commands),
            f"Signals refreshed at {ts}",
        )
    except Exception as exc:
        err = f"Error: {exc}"
        return err, err, err, err


def generate_context(model_choice: str, force_refresh: bool) -> tuple:
    """
    Generate/refresh compressed context with the selected model.

    Returns (context_text, status_text, token_stat, timing_stat, turns_stat).
    """
    global _generation_count
    try:
        init_db()

        # Apply model selection
        if model_choice and model_choice != "[mock — no API key]":
            if model_choice in ANTHROPIC_MODELS:
                os.environ["CLAUDE_MODEL"] = model_choice
            elif "/" in model_choice:
                os.environ["OPENROUTER_MODEL"] = model_choice

        anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
        openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
        use_mock = (
            model_choice == "[mock — no API key]"
            or (not bool(anthropic_key) and not bool(openrouter_key))
        )

        ctx = get_or_generate_context(force_refresh=force_refresh, use_mock=use_mock)
        _generation_count += 1

        status = _compute_status(ctx, use_mock)
        tokens = ctx["token_estimate"]
        gen_ms = ctx.get("generation_time_ms", 0)
        conf = ctx.get("confidence", 0.0)

        return (
            ctx["summary"],
            status,
            f"~{tokens} tokens  |  conf {conf}/100  |  {gen_ms} ms  |  gen #{_generation_count}",
        )
    except Exception as exc:
        err = f"Error generating context: {exc}"
        return err, err, "—"


def copy_context(context_text: str) -> str:
    """Copy context to clipboard (best-effort)."""
    try:
        import pyperclip
        pyperclip.copy(context_text)
        return "Copied to clipboard!"
    except Exception:
        return "Clipboard not available in this environment — select all text above and copy manually."


# ── Interface builder ──────────────────────────────────────────────────────────

_SCENARIO_INSTRUCTIONS = {
    "🎯 New Task — suggest 3 concrete next steps based on my activity":
        "Given this developer context, what should I focus on next? Suggest 3 concrete next steps.",
    "🐛 Debug Session — find likely root causes from my recent changes":
        "I'm debugging an issue. Based on my recent changes and activity, what are the most likely root causes? Where should I look first?",
    "📝 PR Summary — write a pull request description for my commits":
        "Based on this context, write a concise pull request description with: summary (1-2 sentences), changes made (bullet list), testing notes.",
    "☀️ Daily Standup — summarise what I did, am doing, and any blockers":
        "Write my daily standup update (what I did yesterday, what I'm doing today, any blockers) based on this developer context. Keep it to 3 bullet points.",
}


def _apply_scenario(choice: str, context_text: str) -> str:
    """Build a ready-to-paste LLM prompt from the selected scenario and current context."""
    if not choice:
        return "Select a scenario above, then click Build Scenario Prompt."
    instruction = _SCENARIO_INSTRUCTIONS.get(choice, choice)
    if not context_text or len(context_text) < 10:
        return f"Generate context first (Context tab), then click this button.\n\n{instruction}"
    return f"{context_text}\n\n---\n\n{instruction}"


def build_interface() -> gr.Blocks:
    """Construct and return the full Gradio Blocks interface."""
    mono_css = """
    .mono textarea, .mono input { font-family: 'Courier New', monospace; font-size: 12px; }
    .stat-box { border-radius: 8px; padding: 4px; }
    .stats-row { display: flex; flex-wrap: wrap; gap: 8px; }
    .stats-row > div { flex: 1 1 auto; min-width: 140px; }
    """

    with gr.Blocks(title="Ambient Context Aggregator", theme=gr.themes.Soft(), css=mono_css) as demo:

        # ── Header ─────────────────────────────────────────────────────────────
        gr.Markdown(
            """# Ambient Context Aggregator
**Passive developer context tracking** — automatically builds a ≤600-token LLM-ready context block from your files, commits, and shell history.

*Made autonomously using [NEO](https://heyneo.so) — your autonomous AI Agent · [![Install NEO](https://img.shields.io/badge/VS%%20Code-Install%%20NEO-7B61FF?logo=visual-studio-code)](https://marketplace.visualstudio.com/items?itemName=NeoResearchInc.heyneo)*
"""
        )

        # ── Live stats panel ───────────────────────────────────────────────────
        with gr.Row(elem_classes=["stats-row"]):
            stat_tokens = gr.Textbox(
                label="Token Usage",
                value="—",
                interactive=False,
                elem_classes=["mono", "stat-box"],
                scale=1,
            )
            stat_timing = gr.Textbox(
                label="Generation Time",
                value="—",
                interactive=False,
                elem_classes=["mono", "stat-box"],
                scale=1,
            )
            stat_turns = gr.Textbox(
                label="Generations This Session",
                value="0",
                interactive=False,
                elem_classes=["mono", "stat-box"],
                scale=1,
            )

        # ── Global status bar ──────────────────────────────────────────────────
        status_box = gr.Textbox(
            label="Status",
            value="Loading…",
            interactive=False,
            elem_classes=["mono"],
        )

        # ── Tabs ───────────────────────────────────────────────────────────────
        with gr.Tabs():

            # ── Tab 1: Overview (Signals) ──────────────────────────────────────
            with gr.Tab("Overview"):
                with gr.Row():
                    refresh_signals_btn = gr.Button("Refresh Signals", variant="primary")

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Files Changed (Last Hour)")
                        file_panel = gr.Textbox(
                            label="File Events",
                            lines=8,
                            interactive=False,
                            elem_classes=["mono"],
                        )

                    with gr.Column():
                        gr.Markdown("### Recent Git Commits")
                        git_panel = gr.Textbox(
                            label="Git Commits",
                            lines=8,
                            interactive=False,
                            elem_classes=["mono"],
                        )

                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Recent Terminal Commands")
                        cmd_panel = gr.Textbox(
                            label="Terminal History",
                            lines=8,
                            interactive=False,
                            elem_classes=["mono"],
                        )

            # ── Tab 2: Context ─────────────────────────────────────────────────
            with gr.Tab("Context"):
                with gr.Row():
                    model_picker = gr.Dropdown(
                        choices=ALL_MODELS,
                        value=DEFAULT_MODEL if DEFAULT_MODEL in ALL_MODELS else ALL_MODELS[0],
                        label="Model",
                        scale=3,
                    )
                    force_refresh_check = gr.Checkbox(label="Force refresh", value=False, scale=1)
                    generate_btn = gr.Button("Generate Context", variant="primary", scale=2)

                context_panel = gr.Textbox(
                    label="Compressed Context — paste directly into any LLM prompt",
                    lines=18,
                    interactive=False,
                    elem_classes=["mono"],
                )

                with gr.Row():
                    copy_btn = gr.Button("Copy to Clipboard", variant="secondary")
                    copy_status = gr.Textbox(label="", lines=1, interactive=False, scale=3)

                # ── Scenario selector ──────────────────────────────────────────
                with gr.Accordion("Quick Scenarios — build a ready-to-paste prompt", open=True):
                    scenario_radio = gr.Radio(
                        choices=list(_SCENARIO_INSTRUCTIONS.keys()),
                        label="Select a scenario",
                        value=None,
                    )
                    build_scenario_btn = gr.Button("Build Scenario Prompt", variant="primary")
                    scenario_output = gr.Textbox(
                        label="Scenario Prompt — copy and paste into your LLM",
                        lines=6,
                        interactive=True,
                        elem_classes=["mono"],
                    )

            # ── Tab 3: Activity Timeline ───────────────────────────────────────
            with gr.Tab("Timeline"):
                with gr.Row():
                    timeline_hours = gr.Slider(
                        minimum=1, maximum=24, value=8, step=1, label="Hours to show"
                    )
                    refresh_timeline_btn = gr.Button("Refresh Timeline", variant="primary")

                timeline_panel = gr.Textbox(
                    label="Activity Timeline (newest at top)",
                    lines=12,
                    interactive=False,
                    elem_classes=["mono"],
                )

            # ── Tab 4: Meeting Notes ───────────────────────────────────────────
            with gr.Tab("Meeting Notes"):
                with gr.Row():
                    refresh_notes_btn = gr.Button("Scan for Notes", variant="primary")
                    gr.Markdown(
                        "Set `NOTES_DIR` env var to your notes folder. "
                        "Scans `.md` files modified in the last 48h."
                    )

                notes_panel = gr.Textbox(
                    label="Recent Meeting Notes",
                    lines=12,
                    interactive=False,
                    elem_classes=["mono"],
                )

            # ── Tab 5: History & Diff ──────────────────────────────────────────
            with gr.Tab("History & Diff"):
                with gr.Row():
                    refresh_history_btn = gr.Button("Refresh History", variant="primary")
                    refresh_diff_btn = gr.Button("Show Diff", variant="secondary")

                with gr.Row():
                    with gr.Column():
                        diff_panel = gr.Textbox(
                            label="Context Diff (last 2 snapshots)",
                            lines=14,
                            interactive=False,
                            elem_classes=["mono"],
                        )
                    with gr.Column():
                        history_panel = gr.Textbox(
                            label="Context History (last 5 snapshots)",
                            lines=14,
                            interactive=False,
                            elem_classes=["mono"],
                        )

            # ── Tab 6: Stats ───────────────────────────────────────────────────
            with gr.Tab("Stats"):
                refresh_stats_btn = gr.Button("Refresh Stats", variant="primary")
                stats_panel = gr.Textbox(
                    label="Database Statistics",
                    lines=10,
                    interactive=False,
                    elem_classes=["mono"],
                )

        # ── Event wiring ───────────────────────────────────────────────────────

        # Overview tab
        refresh_signals_btn.click(
            fn=refresh_signals,
            inputs=[],
            outputs=[file_panel, git_panel, cmd_panel, status_box],
        )

        # Context tab — generate button also updates live stats panel
        generate_btn.click(
            fn=generate_context,
            inputs=[model_picker, force_refresh_check],
            outputs=[context_panel, status_box, stat_tokens],
        )
        copy_btn.click(fn=copy_context, inputs=[context_panel], outputs=[copy_status])

        # Timeline tab
        refresh_timeline_btn.click(
            fn=lambda h: _fmt_timeline(int(h)),
            inputs=[timeline_hours],
            outputs=[timeline_panel],
        )

        # Notes tab
        refresh_notes_btn.click(fn=_fmt_notes, inputs=[], outputs=[notes_panel])

        # History & Diff tab
        refresh_history_btn.click(fn=_fmt_history, inputs=[], outputs=[history_panel])
        refresh_diff_btn.click(fn=_fmt_diff, inputs=[], outputs=[diff_panel])

        # Stats tab
        refresh_stats_btn.click(fn=_fmt_stats, inputs=[], outputs=[stats_panel])

        # Scenario selector
        build_scenario_btn.click(
            fn=_apply_scenario,
            inputs=[scenario_radio, context_panel],
            outputs=[scenario_output],
        )

        # Populate on load
        def _on_load():
            """Load all panels on initial page render."""
            files, commits, cmds, ctx_text, status = get_dashboard_data()
            tl = _fmt_timeline(8)
            notes = _fmt_notes()
            diff = _fmt_diff()
            hist = _fmt_history()
            stats = _fmt_stats()
            tokens_stat = f"~{len(ctx_text) // 4} tokens"
            return (
                files, commits, cmds,               # overview
                ctx_text,                           # context
                tl,                                 # timeline
                notes,                              # notes
                diff, hist,                         # history
                stats,                              # stats
                status,                             # global status_box
                tokens_stat,                        # live stats panel
            )

        demo.load(
            fn=_on_load,
            inputs=[],
            outputs=[
                file_panel, git_panel, cmd_panel,
                context_panel,
                timeline_panel,
                notes_panel,
                diff_panel, history_panel,
                stats_panel,
                status_box,
                stat_tokens,
            ],
        )

    return demo


# ── Main ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    init_db()
    port = int(os.getenv("GRADIO_PORT", "7860"))
    host = os.getenv("GRADIO_HOST", "0.0.0.0")

    iface = build_interface()
    iface.launch(server_name=host, server_port=port, share=False, show_error=True)
