"""Meeting notes ingestion — scans a notes directory for recently modified Markdown files."""

import os
import re
import time
from pathlib import Path


def _notes_dir() -> Path:
    raw = os.getenv("NOTES_DIR", "")
    if raw:
        return Path(raw).expanduser()
    # Try common locations
    for candidate in [Path.home() / "notes", Path.home() / "Documents" / "notes", Path("notes")]:
        if candidate.is_dir():
            return candidate
    return Path("notes")  # fallback (may not exist)


def _extract_title(content: str, filename: str) -> str:
    """Extract the first H1 heading or fall back to the filename stem."""
    match = re.search(r"^#\s+(.+)$", content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return Path(filename).stem.replace("-", " ").replace("_", " ").title()


def _extract_excerpt(content: str, max_chars: int = 300) -> str:
    """Return the first meaningful block of text (skipping headings)."""
    lines = []
    for line in content.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            lines.append(stripped)
        if sum(len(l) for l in lines) >= max_chars:
            break
    text = " ".join(lines)
    return text[:max_chars] + ("…" if len(text) > max_chars else "")


def scan_meeting_notes(since_hours: int = None) -> list:
    """
    Return a list of recently modified Markdown files from the notes directory.

    Each entry:
        {
            "path": str,
            "title": str,
            "excerpt": str,
            "modified_at": float,
            "word_count": int,
        }
    """
    if since_hours is None:
        since_hours = int(os.getenv("NOTES_SINCE_HOURS", "48"))

    cutoff = time.time() - since_hours * 3600
    notes_path = _notes_dir()

    if not notes_path.exists():
        return []

    results = []
    for md_file in sorted(notes_path.rglob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
        try:
            stat = md_file.stat()
            if stat.st_mtime < cutoff:
                continue
            content = md_file.read_text(errors="ignore")
            results.append(
                {
                    "path": str(md_file),
                    "title": _extract_title(content, md_file.name),
                    "excerpt": _extract_excerpt(content),
                    "modified_at": stat.st_mtime,
                    "word_count": len(content.split()),
                }
            )
        except OSError:
            continue

    limit = int(os.getenv("MAX_NOTES", "10"))
    return results[:limit]


def format_notes_for_context(notes: list) -> str:
    """Format meeting notes as a concise block for LLM context injection."""
    if not notes:
        return ""
    lines = ["**Recent Meeting Notes / Docs:**"]
    for n in notes:
        from datetime import datetime
        ts = datetime.fromtimestamp(n["modified_at"]).strftime("%Y-%m-%d %H:%M")
        lines.append(f"- [{ts}] **{n['title']}** ({n['word_count']} words)")
        if n["excerpt"]:
            lines.append(f"  > {n['excerpt'][:150]}")
    return "\n".join(lines)
