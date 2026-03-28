"""Terminal history parser — reads .bash_history, .zsh_history, etc."""

import os
import time
from pathlib import Path


def get_history_file_paths() -> list:
    """Return list of existing shell history files on this system."""
    home = Path.home()
    env_override = os.getenv("HISTORY_FILE", "")
    candidates = [
        env_override,
        str(home / ".bash_history"),
        str(home / ".zsh_history"),
        str(home / ".sh_history"),
        str(home / ".local" / "share" / "fish" / "fish_history"),
    ]
    return [p for p in candidates if p and Path(p).exists()]


def parse_bash_history(path: str, limit: int = 100) -> list:
    """Parse a plain bash history file (one command per line)."""
    commands = []
    try:
        with open(path, "r", errors="ignore") as fh:
            lines = fh.readlines()
        for line in reversed(lines):
            line = line.strip()
            if line and not line.startswith("#"):
                commands.append({"command": line, "timestamp": time.time()})
                if len(commands) >= limit:
                    break
    except OSError:
        pass
    return commands


def parse_zsh_history(path: str, limit: int = 100) -> list:
    """Parse zsh extended history format: ': <ts>:<duration>;<cmd>'."""
    commands = []
    try:
        with open(path, "r", errors="ignore") as fh:
            content = fh.read()
        lines = content.splitlines()
        for line in reversed(lines):
            line = line.strip()
            if not line:
                continue
            if line.startswith(": ") and ";" in line:
                try:
                    meta, cmd = line.split(";", 1)
                    parts = meta.split(":")
                    ts = float(parts[1].strip()) if len(parts) > 1 else time.time()
                    commands.append({"command": cmd.strip(), "timestamp": ts})
                except Exception:
                    commands.append({"command": line, "timestamp": time.time()})
            else:
                commands.append({"command": line, "timestamp": time.time()})
            if len(commands) >= limit:
                break
    except OSError:
        pass
    return commands


def parse_history_file(path: str, limit: int = 100) -> list:
    """Dispatch to the right parser based on filename."""
    if "zsh" in Path(path).name:
        return parse_zsh_history(path, limit)
    return parse_bash_history(path, limit)


def get_recent_commands(limit: int = 100) -> list:
    """Return the most recent unique shell commands from detected history files."""
    limit = int(os.getenv("MAX_HISTORY_LINES", str(limit)))
    history_files = get_history_file_paths()

    all_commands: list = []
    for path in history_files:
        all_commands.extend(parse_history_file(path, limit))

    # Deduplicate while preserving order
    seen: set = set()
    unique: list = []
    for cmd in all_commands:
        text = cmd["command"]
        if text not in seen:
            seen.add(text)
            unique.append(cmd)

    return unique[:limit]
