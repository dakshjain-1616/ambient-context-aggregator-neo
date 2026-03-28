"""
Focus scorer — infers the developer's current work type and focus area
from activity signals, returning a confidence-scored result.
"""

import re
from pathlib import Path

# Signal patterns per work type. Each sub-list is checked against the
# corresponding signal texts; each match increments the raw score.
_PATTERNS: dict = {
    "testing": {
        "commands": [r"\bpytest\b", r"\btest\b", r"--cov", r"\bjest\b", r"\bmocha\b", r"\bvitest\b"],
        "files": [r"test_", r"_test\.py$", r"\.spec\.", r"__tests__", r"_spec\."],
        "commits": [r"\btest\b", r"\bspec\b", r"\bcoverage\b", r"\bfixture\b"],
    },
    "debugging": {
        "commands": [r"\bpdb\b", r"\bipdb\b", r"\bbreakpoint\b", r"\bdebugpy\b", r"\bstrace\b"],
        "files": [],
        "commits": [r"\bfix\b", r"\bbug\b", r"\bdebug\b", r"\bhotfix\b", r"\brevert\b"],
    },
    "refactoring": {
        "commands": [r"\bblack\b", r"\bisort\b", r"\bflake8\b", r"\bmypy\b", r"\bruff\b", r"\bpylint\b"],
        "files": [],
        "commits": [r"\brefactor\b", r"\bclean\b", r"\brename\b", r"\breorg\b", r"\bmove\b", r"\bsimplif"],
    },
    "feature_development": {
        "commands": [r"\bgit commit\b", r"\bgit push\b", r"\bnpm run build\b", r"\bpip install\b"],
        "files": [],
        "commits": [r"\badd\b", r"\bimplement\b", r"\bfeature\b", r"\bnew\b", r"\bcreate\b", r"\bintroduce\b"],
    },
    "infrastructure": {
        "commands": [r"\bdocker\b", r"\bkubectl\b", r"\bterraform\b", r"\bansible\b", r"\bhelm\b", r"\bnginx\b"],
        "files": [r"\.ya?ml$", r"Dockerfile", r"docker-compose", r"\.tf$", r"\.hcl$"],
        "commits": [r"\bdeploy\b", r"\binfra\b", r"\bci\b", r"\bpipeline\b", r"\bkube\b", r"\bdocker\b"],
    },
    "code_review": {
        "commands": [r"\bgit diff\b", r"\bgit log\b", r"\bgh pr\b", r"\bgit blame\b", r"\bgit show\b"],
        "files": [],
        "commits": [r"\breview\b", r"\bpr\b", r"\bmerge\b", r"\bfeedback\b"],
    },
    "documentation": {
        "commands": [r"\bsphinx\b", r"\bmkdocs\b", r"\bpandoc\b"],
        "files": [r"\.md$", r"\.rst$", r"docs/", r"README"],
        "commits": [r"\bdoc\b", r"\bchangelog\b", r"\breadme\b", r"\bcomment\b"],
    },
}

_WEIGHTS = {"commands": 2, "files": 3, "commits": 2}


def _count_matches(patterns: list, texts: list) -> int:
    total = 0
    for text in texts:
        for pat in patterns:
            if re.search(pat, text, re.IGNORECASE):
                total += 1
                break
    return total


def score_focus(signals: dict) -> dict:
    """
    Analyse signals and return a focus analysis dict.

    Returns:
        {
            "work_type": str,          # top inferred work type
            "confidence": float,       # 0.0–1.0
            "scores": dict,            # normalised scores per category
            "top_files": list[str],    # most recently touched filenames
            "session_summary": str,    # human-readable summary
        }
    """
    files = signals.get("file_events", [])
    commits = signals.get("git_commits", [])
    commands = signals.get("terminal_commands", [])

    file_names = [Path(f["path"]).name for f in files]
    commit_msgs = [c["message"] for c in commits]
    cmd_texts = [c["command"] for c in commands]

    raw_scores: dict = {}
    for work_type, patterns in _PATTERNS.items():
        score = (
            _count_matches(patterns["commands"], cmd_texts) * _WEIGHTS["commands"]
            + _count_matches(patterns["files"], file_names) * _WEIGHTS["files"]
            + _count_matches(patterns["commits"], commit_msgs) * _WEIGHTS["commits"]
        )
        raw_scores[work_type] = score

    total = sum(raw_scores.values()) or 1
    normalised = {k: round(v / total, 3) for k, v in raw_scores.items()}

    top_type = max(raw_scores, key=raw_scores.get)
    top_raw = raw_scores[top_type]

    # Confidence: scaled by how dominant the top category is
    confidence = min(1.0, round(top_raw / max(8, total * 0.25), 3))

    # Deduplicated top files
    seen: set = set()
    top_files = []
    for f in files:
        name = Path(f["path"]).name
        if name not in seen:
            seen.add(name)
            top_files.append(name)
        if len(top_files) >= 5:
            break

    work_label = top_type.replace("_", " ").title()
    confidence_label = "high" if confidence > 0.5 else "medium" if confidence > 0.2 else "low"

    session_summary = (
        f"Primarily {work_label} ({confidence_label} confidence, {confidence:.0%}). "
        f"{len(files)} file event(s), {len(commits)} commit(s), {len(commands)} command(s) tracked."
    )

    return {
        "work_type": top_type,
        "confidence": confidence,
        "scores": normalised,
        "top_files": top_files,
        "session_summary": session_summary,
    }
