"""Command-line interface for the Ambient Context Aggregator."""

import os
import sys
import signal
import argparse
from datetime import datetime
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()


# ── Subcommand handlers ────────────────────────────────────────────────────────

def cmd_get(args) -> None:
    """Print the current compressed context."""
    from ambient_context.database import init_db
    from ambient_context.compressor import get_or_generate_context

    init_db()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    use_mock = (not bool(anthropic_key) and not bool(openrouter_key)) or args.mock

    with console.status("[bold green]Generating context…"):
        result = get_or_generate_context(force_refresh=args.refresh, use_mock=use_mock)

    summary = result["summary"]
    tokens = result["token_estimate"]
    conf = result.get("confidence", 0.0)
    provider = result.get("provider", "mock")
    gen_ms = result.get("generation_time_ms", 0)

    if args.raw:
        print(summary)
    else:
        meta = (
            f"~{tokens} tokens  |  confidence {conf}/100  |  "
            f"{provider}  |  {gen_ms}ms"
        )
        console.print(
            Panel(
                summary,
                title=f"[bold cyan]Ambient Context[/bold cyan]  ({meta})",
                border_style="cyan",
                padding=(1, 2),
            )
        )

    if args.copy:
        try:
            import pyperclip
            pyperclip.copy(summary)
            console.print("[green]✓ Copied to clipboard[/green]")
        except Exception as exc:
            console.print(f"[yellow]Could not copy to clipboard: {exc}[/yellow]")

    if args.output:
        out_path = Path(args.output)
        out_path.write_text(summary)
        console.print(f"[green]✓ Saved to {out_path}[/green]")


def cmd_watch(args) -> None:
    """Start the background file watcher."""
    from ambient_context.database import init_db
    from ambient_context.watcher import start_watcher
    import time

    init_db()
    watch_dir = args.dir or os.getenv("WATCH_DIR", ".")

    console.print(f"[green]Watching:[/green] {Path(watch_dir).resolve()}")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    def on_change(path: str, event_type: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        console.print(f"  [dim]{ts}[/dim]  [dim]{event_type:10s}[/dim]  {path}")

    watcher = start_watcher(watch_dir=watch_dir, callback=on_change)

    def _stop(signum, frame):
        console.print("\n[yellow]Stopping watcher…[/yellow]")
        watcher.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while watcher.is_running():
        time.sleep(0.5)


def cmd_serve(args) -> None:
    """Start the FastAPI REST server."""
    from ambient_context.api import serve

    console.print(
        f"[green]Starting API server on[/green] "
        f"{os.getenv('API_HOST', '0.0.0.0')}:{os.getenv('API_PORT', '8000')}"
    )
    serve()


def cmd_signals(args) -> None:
    """Display current signals in the terminal."""
    from ambient_context.database import (
        init_db,
        get_recent_file_events,
        get_recent_git_commits,
        get_recent_terminal_commands,
        get_db_stats,
    )

    init_db()

    files = get_recent_file_events(limit=10)
    commits = get_recent_git_commits(limit=5)
    commands = get_recent_terminal_commands(limit=10)

    t1 = Table(title="Recent File Events", show_header=True)
    t1.add_column("Time", style="dim")
    t1.add_column("File", style="cyan")
    t1.add_column("Event", style="magenta")
    for f in files:
        ts = datetime.fromtimestamp(f["timestamp"]).strftime("%H:%M:%S")
        t1.add_row(ts, Path(f["path"]).name, f["event_type"])
    console.print(t1)

    t2 = Table(title="Recent Git Commits", show_header=True)
    t2.add_column("Hash", style="yellow")
    t2.add_column("Date", style="dim")
    t2.add_column("Author", style="green")
    t2.add_column("Message")
    for c in commits:
        ts = datetime.fromtimestamp(c["timestamp"]).strftime("%Y-%m-%d")
        t2.add_row(c["hash"], ts, c["author"].split("<")[0].strip()[:20], c["message"][:55])
    console.print(t2)

    t3 = Table(title="Recent Terminal Commands", show_header=True)
    t3.add_column("Time", style="dim")
    t3.add_column("Command", style="blue")
    for c in commands:
        ts = datetime.fromtimestamp(c["timestamp"]).strftime("%H:%M:%S")
        t3.add_row(ts, c["command"][:80])
    console.print(t3)

    if args.stats:
        stats = get_db_stats()
        t4 = Table(title="Database Stats", show_header=True)
        t4.add_column("Table", style="cyan")
        t4.add_column("Rows", justify="right")
        for table, count in stats.items():
            t4.add_row(table, str(count))
        console.print(t4)


def cmd_timeline(args) -> None:
    """Show activity timeline for the last N hours."""
    from ambient_context.database import init_db
    from ambient_context.timeline import build_hourly_timeline, detect_focus_sessions, format_timeline_text

    init_db()
    hours = args.hours or int(os.getenv("TIMELINE_HOURS", "8"))
    timeline = build_hourly_timeline(hours=hours)
    sessions = detect_focus_sessions(timeline)

    console.print(
        Panel(
            format_timeline_text(timeline),
            title=f"[bold cyan]Activity Timeline — Last {hours} Hours[/bold cyan]",
            border_style="blue",
        )
    )

    if sessions:
        console.print("\n[bold]Focus Sessions Detected:[/bold]")
        for s in sessions:
            console.print(
                f"  {s['start']} → {s['end']}  "
                f"({s['duration_hours']}h, {s['total_events']} events)"
            )
    else:
        console.print("[dim]No focus sessions detected in this window.[/dim]")


def cmd_diff(args) -> None:
    """Show what changed between the last two context snapshots."""
    from ambient_context.database import init_db
    from ambient_context.context_diff import get_diff_report

    init_db()
    report = get_diff_report()
    console.print(
        Panel(
            report,
            title="[bold yellow]Context Diff[/bold yellow]",
            border_style="yellow",
        )
    )


def cmd_stats(args) -> None:
    """Show signal stats and database row counts."""
    from ambient_context.database import init_db, get_db_stats, get_signal_stats

    init_db()
    db = get_db_stats()
    stats = get_signal_stats()

    t = Table(title="Signal Statistics", show_header=True)
    t.add_column("Metric", style="cyan")
    t.add_column("Value", style="green", justify="right")
    t.add_row("File events (last hour)", str(stats["file_events_last_hour"]))
    t.add_row("Commands (last 24h)", str(stats["commands_last_24h"]))
    t.add_row("Total git commits", str(stats["total_commits"]))
    t.add_row("Contexts generated", str(stats["total_contexts_generated"]))
    if stats.get("latest_context_at"):
        ts = datetime.fromtimestamp(stats["latest_context_at"]).strftime("%Y-%m-%d %H:%M:%S")
        t.add_row("Last context at", ts)
        t.add_row("Last token estimate", f"~{stats['latest_token_estimate']}")
        t.add_row("Last provider", stats.get("latest_provider", "mock"))
    console.print(t)

    t2 = Table(title="Database Rows", show_header=True)
    t2.add_column("Table", style="yellow")
    t2.add_column("Count", justify="right")
    for table, count in db.items():
        t2.add_row(table, str(count))
    console.print(t2)


def cmd_export(args) -> None:
    """Export context to a file (markdown or JSON)."""
    import json as _json
    from ambient_context.database import init_db
    from ambient_context.compressor import get_or_generate_context

    init_db()
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
    use_mock = (not bool(anthropic_key) and not bool(openrouter_key)) or getattr(args, "mock", False)

    with console.status("[bold green]Generating context for export…"):
        result = get_or_generate_context(force_refresh=True, use_mock=use_mock)

    fmt = getattr(args, "format", "md")
    ts_str = datetime.fromtimestamp(result["created_at"]).strftime("%Y%m%d_%H%M%S")
    default_name = f"context_{ts_str}.{fmt}"
    out_path = Path(getattr(args, "output", None) or default_name)

    if fmt == "json":
        content = _json.dumps(
            {
                "summary": result["summary"],
                "token_estimate": result["token_estimate"],
                "provider": result.get("provider", "mock"),
                "generation_time_ms": result.get("generation_time_ms", 0),
                "focus": result.get("focus", {}),
                "created_at": result["created_at"],
                "created_at_iso": datetime.fromtimestamp(result["created_at"]).isoformat(),
            },
            indent=2,
            default=str,
        )
    else:
        ts_iso = datetime.fromtimestamp(result["created_at"]).isoformat()
        provider = result.get("provider", "mock")
        tokens = result["token_estimate"]
        content = (
            f"# Ambient Context Export\n\n"
            f"**Generated:** {ts_iso}  \n"
            f"**Provider:** {provider}  \n"
            f"**Tokens:** ~{tokens}  \n\n"
            f"---\n\n{result['summary']}\n"
        )

    out_path.write_text(content)
    console.print(f"[green]✓ Exported to[/green] {out_path}")


def cmd_focus(args) -> None:
    """Show inferred developer focus analysis (confidence + signal breakdown)."""
    from ambient_context.database import init_db
    from ambient_context.compressor import build_signals_dict
    from ambient_context.timeline import compute_confidence_score, build_hourly_timeline

    init_db()
    signals = build_signals_dict(include_notes=False)
    confidence = compute_confidence_score(signals)

    files = signals.get("file_events", [])
    commits = signals.get("git_commits", [])
    commands = signals.get("terminal_commands", [])

    t = Table(title="Developer Focus Analysis", show_header=True)
    t.add_column("Signal", style="cyan")
    t.add_column("Count", justify="right", style="green")
    t.add_column("Weight", justify="right")
    t.add_row("File events (last hour)", str(len(files)), "35pt")
    t.add_row("Git commits", str(len(commits)), "25pt")
    t.add_row("Terminal commands", str(len(commands)), "30pt")
    console.print(t)

    bar_len = int(confidence / 5)
    bar = "█" * bar_len + "░" * (20 - bar_len)
    conf_color = "green" if confidence >= 60 else "yellow" if confidence >= 30 else "red"
    console.print(
        f"\n[bold]Confidence:[/bold] [{conf_color}]{bar}[/{conf_color}] {confidence}/100"
    )

    # Show active file types
    from pathlib import Path as _Path
    ext_counts: dict = {}
    for f in files:
        ext = _Path(f["path"]).suffix.lower() or "other"
        ext_counts[ext] = ext_counts.get(ext, 0) + 1
    if ext_counts:
        top_ext = sorted(ext_counts.items(), key=lambda x: -x[1])[:3]
        console.print(f"[bold]Top file types:[/bold] {', '.join(f'{e}({c})' for e, c in top_ext)}")


def cmd_notes(args) -> None:
    """List recently modified meeting notes."""
    from ambient_context.meeting_notes import scan_meeting_notes

    hours = args.hours or int(os.getenv("NOTES_SINCE_HOURS", "48"))
    notes = scan_meeting_notes(since_hours=hours)

    if not notes:
        console.print(
            f"[yellow]No meeting notes found in the last {hours}h.[/yellow]\n"
            f"Set NOTES_DIR to point at your notes folder."
        )
        return

    t = Table(title=f"Meeting Notes — Last {hours}h", show_header=True)
    t.add_column("Modified", style="dim")
    t.add_column("Title", style="cyan")
    t.add_column("Words", justify="right")
    t.add_column("Excerpt")

    for n in notes:
        ts = datetime.fromtimestamp(n["modified_at"]).strftime("%Y-%m-%d %H:%M")
        t.add_row(ts, n["title"][:40], str(n["word_count"]), n["excerpt"][:60])

    console.print(t)


# ── Entry point ────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="ambient_context",
        description="Ambient Context Aggregator — passive developer context tracking",
    )
    sub = parser.add_subparsers(dest="command")

    # get
    p_get = sub.add_parser("get", help="Print current context summary")
    p_get.add_argument("--refresh", action="store_true", help="Force refresh (bypass cache)")
    p_get.add_argument("--mock", action="store_true", help="Use mock mode (no LLM call)")
    p_get.add_argument("--raw", action="store_true", help="Plain text output (no formatting)")
    p_get.add_argument("--copy", action="store_true", help="Copy result to clipboard")
    p_get.add_argument("--output", "-o", type=str, help="Save context to a file")
    p_get.add_argument("--model", type=str, default=None,
                       help="Override model ID (e.g. claude-sonnet-4-6 or openai/gpt-5.4-mini)")

    # watch
    p_watch = sub.add_parser("watch", help="Start background file watcher")
    p_watch.add_argument("--dir", type=str, help="Directory to watch (default: WATCH_DIR env or .)")

    # serve
    sub.add_parser("serve", help="Start FastAPI REST server")

    # signals
    p_signals = sub.add_parser("signals", help="Show raw collected signals")
    p_signals.add_argument("--stats", action="store_true", help="Include database row counts")

    # timeline
    p_timeline = sub.add_parser("timeline", help="Show activity timeline")
    p_timeline.add_argument("--hours", type=int, default=None, help="Hours to look back (default: 8)")

    # diff
    sub.add_parser("diff", help="Show diff between last two context snapshots")

    # notes
    p_notes = sub.add_parser("notes", help="List recent meeting notes")
    p_notes.add_argument("--hours", type=int, default=None, help="Hours to look back (default: 48)")

    # stats
    sub.add_parser("stats", help="Show signal stats and database row counts")

    # export
    p_export = sub.add_parser("export", help="Export current context to a file")
    p_export.add_argument("--format", choices=["md", "json"], default="md",
                          help="Output format (default: md)")
    p_export.add_argument("--output", "-o", type=str, default=None, help="Output file path")
    p_export.add_argument("--mock", action="store_true", help="Use mock mode")

    # focus
    sub.add_parser("focus", help="Show inferred developer focus analysis")

    args = parser.parse_args()

    dispatch = {
        "get": cmd_get,
        "watch": cmd_watch,
        "serve": cmd_serve,
        "signals": cmd_signals,
        "timeline": cmd_timeline,
        "diff": cmd_diff,
        "notes": cmd_notes,
        "stats": cmd_stats,
        "export": cmd_export,
        "focus": cmd_focus,
    }

    fn = dispatch.get(args.command)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
