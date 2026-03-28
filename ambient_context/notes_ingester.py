"""Meeting notes ingester — parses markdown/txt notes files for context signals."""

import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


NOTES_EXTENSIONS = {".md", ".txt", ".rst"}


def get_notes_dir() -> Optional[Path]:
    """Return the configured notes directory if it exists."""
    notes_dir = os.getenv("NOTES_DIR", "")
    if not notes_dir:
        return None
    p = Path(notes_dir)
    return p if p.is_dir() else None


def parse_note_file(path: Path) -> dict:
    """Parse a single notes file, extracting title, key points, and action items."""
    try:
        content = path.read_text(errors="ignore").strip()
    except OSError:
        return {}

    if not content:
        return {}

    # Title: first markdown heading or filename stem
    title = path.stem.replace("_", " ").replace("-", " ").title()
    heading_match = re.search(r"^#+ (.+)$", content, re.MULTILINE)
    if heading_match:
        title = heading_match.group(1).strip()

    # Action items: - [ ] patterns, TODO:, ACTION:
    action_items = re.findall(
        r"(?:- \[ \]|TODO:|ACTION:)\s*(.+)", content, re.IGNORECASE
    )

    # Key bullet points
    bullet_points = re.findall(r"^[\-\*\+] (.+)$", content, re.MULTILINE)[:10]

    mtime = path.stat().st_mtime

    return {
        "path": str(path),
        "title": title,
        "modified_at": mtime,
        "modified_at_iso": datetime.fromtimestamp(mtime).isoformat(),
        "size_bytes": path.stat().st_size,
        "content_preview": content[:500],
        "action_items": [a.strip() for a in action_items[:5]],
        "key_points": [b.strip() for b in bullet_points[:8]],
        "word_count": len(content.split()),
    }


def get_recent_notes(limit: int = None) -> list:
    """Return recently modified notes files, newest first."""
    max_files = int(os.getenv("NOTES_MAX_FILES", "10"))
    max_age_days = float(os.getenv("NOTES_MAX_AGE_DAYS", "7"))
    if limit is None:
        limit = max_files

    notes_dir = get_notes_dir()
    if not notes_dir:
        return []

    cutoff = time.time() - (max_age_days * 86400)
    candidates = []

    for ext in NOTES_EXTENSIONS:
        for fpath in notes_dir.rglob(f"*{ext}"):
            try:
                if fpath.stat().st_mtime >= cutoff:
                    candidates.append(fpath)
            except OSError:
                pass

    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    parsed = []
    for p in candidates[:limit]:
        note = parse_note_file(p)
        if note:
            parsed.append(note)
    return parsed


def format_notes_for_context(notes: list) -> str:
    """Format parsed notes into a compact context block."""
    if not notes:
        return ""

    parts = ["**Meeting Notes & Planning Docs:**"]
    for note in notes[:5]:
        parts.append(f"\n### {note['title']}")
        if note.get("action_items"):
            parts.append("Actions: " + "; ".join(note["action_items"][:3]))
        elif note.get("key_points"):
            parts.append("Points: " + "; ".join(note["key_points"][:3]))
        elif note.get("content_preview"):
            preview = note["content_preview"][:200].replace("\n", " ").strip()
            parts.append(f"Preview: {preview}…")

    return "\n".join(parts)
