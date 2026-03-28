"""Activity timeline — aggregates developer signals into hourly buckets with focus detection."""

import os
import time
from collections import defaultdict
from datetime import datetime, timedelta


def build_hourly_timeline(hours: int = 8) -> list:
    """
    Group file events and terminal commands into hourly buckets.

    Returns a list of dicts, newest-first:
        {
            "hour_label":  str,   # e.g. "14:00"
            "date_label":  str,   # e.g. "2024-01-15"
            "file_events": int,
            "commands":    int,
            "total":       int,
            "bar":         str,   # ASCII mini-bar
            "focus_score": float, # 0-1 intensity relative to peak hour
        }
    """
    from .database import get_recent_file_events, get_recent_terminal_commands

    since_seconds = hours * 3600
    files = get_recent_file_events(limit=500, since_seconds=since_seconds)
    commands = get_recent_terminal_commands(limit=500)

    now = time.time()
    cutoff = now - since_seconds

    buckets: dict = defaultdict(lambda: {"file_events": 0, "commands": 0})

    for f in files:
        if f["timestamp"] >= cutoff:
            dt = datetime.fromtimestamp(f["timestamp"])
            key = dt.strftime("%Y-%m-%d %H")
            buckets[key]["file_events"] += 1

    for c in commands:
        if c["timestamp"] >= cutoff:
            dt = datetime.fromtimestamp(c["timestamp"])
            key = dt.strftime("%Y-%m-%d %H")
            buckets[key]["commands"] += 1

    # Fill in empty hours
    result = []
    for h in range(hours):
        dt = datetime.fromtimestamp(now - h * 3600)
        key = dt.strftime("%Y-%m-%d %H")
        b = buckets.get(key, {"file_events": 0, "commands": 0})
        total = b["file_events"] + b["commands"]
        result.append(
            {
                "hour_label": dt.strftime("%H:00"),
                "date_label": dt.strftime("%Y-%m-%d"),
                "file_events": b["file_events"],
                "commands": b["commands"],
                "total": total,
                "bar": "",         # filled in below
                "focus_score": 0.0,
            }
        )

    # Compute focus scores and bars
    peak = max((r["total"] for r in result), default=1) or 1
    bar_chars = " ▁▂▃▄▅▆▇█"
    for r in result:
        r["focus_score"] = round(r["total"] / peak, 2)
        idx = int(r["focus_score"] * (len(bar_chars) - 1))
        r["bar"] = bar_chars[idx]

    return result


def detect_focus_sessions(timeline: list, min_activity: int = 2) -> list:
    """
    Identify contiguous blocks of active hours as 'focus sessions'.

    Returns list of:
        {"start": str, "end": str, "total_events": int, "duration_hours": int}
    """
    sessions = []
    active = [r for r in reversed(timeline) if r["total"] >= min_activity]

    if not active:
        return sessions

    # Group contiguous hours (simple approach: gap > 1h breaks session)
    current_session = [active[0]]
    for i in range(1, len(active)):
        prev_label = current_session[-1]["date_label"] + " " + current_session[-1]["hour_label"][:2]
        curr_label = active[i]["date_label"] + " " + active[i]["hour_label"][:2]
        try:
            prev_dt = datetime.strptime(prev_label, "%Y-%m-%d %H")
            curr_dt = datetime.strptime(curr_label, "%Y-%m-%d %H")
            gap = abs((curr_dt - prev_dt).total_seconds())
        except ValueError:
            gap = 9999
        if gap <= 3600:
            current_session.append(active[i])
        else:
            if current_session:
                sessions.append(_session_summary(current_session))
            current_session = [active[i]]

    if current_session:
        sessions.append(_session_summary(current_session))

    return sessions


def _session_summary(hours: list) -> dict:
    total = sum(h["total"] for h in hours)
    return {
        "start": f"{hours[0]['date_label']} {hours[0]['hour_label']}",
        "end": f"{hours[-1]['date_label']} {hours[-1]['hour_label']}",
        "total_events": total,
        "duration_hours": len(hours),
    }


def format_timeline_text(timeline: list) -> str:
    """Render the timeline as a readable text block."""
    if not timeline:
        return "No activity data available."
    lines = ["Hour   Files  Cmds  Activity"]
    lines.append("─" * 34)
    for r in timeline:
        bar = r["bar"] * min(20, r["total"])
        lines.append(
            f"{r['hour_label']}  {r['file_events']:5d}  {r['commands']:4d}  {bar}"
        )
    return "\n".join(lines)


def compute_confidence_score(signals: dict) -> float:
    """
    Return a 0-100 confidence score based on signal richness.

    Higher = more data available to generate an accurate context.
    """
    files = len(signals.get("file_events", []))
    commits = len(signals.get("git_commits", []))
    commands = len(signals.get("terminal_commands", []))
    notes = len(signals.get("meeting_notes", []))

    score = 0.0
    score += min(files / 20.0, 1.0) * 35      # up to 35 pts for file events
    score += min(commits / 5.0, 1.0) * 25     # up to 25 pts for git commits
    score += min(commands / 30.0, 1.0) * 30   # up to 30 pts for commands
    score += min(notes / 2.0, 1.0) * 10       # up to 10 pts for notes

    return round(score, 1)
