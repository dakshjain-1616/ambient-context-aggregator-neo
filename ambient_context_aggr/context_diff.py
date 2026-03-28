"""Context diff — compare the two most recent context snapshots to surface what changed."""

import json
import time
from datetime import datetime


def _parse_signals(summary_row: dict) -> dict:
    """Extract signals dict from a context summary DB row."""
    raw = summary_row.get("signals_json") or summary_row.get("signals") or "{}"
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except Exception:
            return {}
    if isinstance(raw, dict):
        return raw
    return {}


def get_recent_summaries(n: int = 2) -> list:
    """Return the N most recent context summaries from the database."""
    from .database import get_connection

    conn = get_connection()
    rows = conn.execute(
        "SELECT summary, token_estimate, signals_json, created_at "
        "FROM context_summaries ORDER BY created_at DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def compute_context_diff(old: dict, new: dict) -> dict:
    """
    Compare two context summary rows and return a structured diff.

    Returns:
        {
            "elapsed_seconds":  float,
            "token_delta":      int,
            "new_file_count":   int,
            "new_commit_count": int,
            "new_cmd_count":    int,
            "new_files":        list[str],
            "new_commits":      list[str],
            "summary":          str,   # human-readable diff description
        }
    """
    old_signals = _parse_signals(old)
    new_signals = _parse_signals(new)

    elapsed = new.get("created_at", time.time()) - old.get("created_at", time.time())

    # File paths
    old_files = {f["path"] for f in old_signals.get("file_events", [])}
    new_files_all = new_signals.get("file_events", [])
    added_files = [f["path"] for f in new_files_all if f["path"] not in old_files]

    # Commit hashes
    old_hashes = {c["hash"] for c in old_signals.get("git_commits", [])}
    new_commits_all = new_signals.get("git_commits", [])
    added_commits = [c for c in new_commits_all if c["hash"] not in old_hashes]

    # Command counts
    old_cmd_count = len(old_signals.get("terminal_commands", []))
    new_cmd_count = len(new_signals.get("terminal_commands", []))
    cmd_delta = max(0, new_cmd_count - old_cmd_count)

    token_delta = new.get("token_estimate", 0) - old.get("token_estimate", 0)

    # Build human-readable summary
    parts = []
    if added_files:
        names = [p.split("/")[-1] for p in added_files[:5]]
        parts.append(f"{len(added_files)} new file event(s): {', '.join(names)}")
    if added_commits:
        msgs = [c["message"][:40] for c in added_commits[:3]]
        parts.append(f"{len(added_commits)} new commit(s): {'; '.join(msgs)}")
    if cmd_delta > 0:
        parts.append(f"{cmd_delta} more terminal command(s) tracked")
    if not parts:
        parts.append("No significant changes since last snapshot")

    elapsed_str = f"{int(elapsed // 60)}m {int(elapsed % 60)}s" if elapsed >= 60 else f"{int(elapsed)}s"

    return {
        "elapsed_seconds": round(elapsed, 1),
        "elapsed_label": elapsed_str,
        "token_delta": token_delta,
        "new_file_count": len(added_files),
        "new_commit_count": len(added_commits),
        "new_cmd_count": cmd_delta,
        "new_files": added_files[:10],
        "new_commits": [c["hash"] + " " + c["message"][:50] for c in added_commits[:5]],
        "summary": "; ".join(parts),
    }


def get_diff_report() -> str:
    """
    High-level function: fetch last 2 snapshots and return a formatted diff string.
    Returns a placeholder message when fewer than 2 snapshots exist.
    """
    rows = get_recent_summaries(2)
    if len(rows) < 2:
        return "Not enough snapshots yet — refresh context at least twice to see a diff."

    new_row, old_row = rows[0], rows[1]
    diff = compute_context_diff(old=old_row, new=new_row)

    from datetime import datetime
    old_ts = datetime.fromtimestamp(old_row["created_at"]).strftime("%H:%M:%S")
    new_ts = datetime.fromtimestamp(new_row["created_at"]).strftime("%H:%M:%S")

    lines = [
        f"## Context Diff  ({old_ts} → {new_ts}, elapsed {diff['elapsed_label']})",
        "",
        f"**Token change:** {diff['token_delta']:+d}",
        f"**New file events:** {diff['new_file_count']}",
        f"**New commits:** {diff['new_commit_count']}",
        f"**Additional commands:** {diff['new_cmd_count']}",
        "",
        "**What changed:**",
        diff["summary"],
    ]

    if diff["new_files"]:
        lines.append("\n**New files touched:**")
        for f in diff["new_files"]:
            lines.append(f"  - {f.split('/')[-1]}")

    if diff["new_commits"]:
        lines.append("\n**New commits:**")
        for c in diff["new_commits"]:
            lines.append(f"  - {c}")

    return "\n".join(lines)
