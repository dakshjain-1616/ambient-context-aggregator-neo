"""LLM context compressor — turns raw developer signals into a concise context summary.

Supports Anthropic Claude (ANTHROPIC_API_KEY) and OpenRouter (OPENROUTER_API_KEY).
Falls back to a mock template when no API key is available.
"""

import os
import json
import time
from pathlib import Path

from .database import (
    get_recent_file_events,
    get_recent_git_commits,
    get_recent_terminal_commands,
    save_context_summary,
    get_latest_context_summary,
)

# ── Config ─────────────────────────────────────────────────────────────────────

CACHE_TTL = int(os.getenv("CONTEXT_CACHE_TTL", "300"))
MAX_RETRIES = int(os.getenv("LLM_MAX_RETRIES", "3"))
RETRY_BASE_DELAY = float(os.getenv("LLM_RETRY_BASE_DELAY", "1.0"))

# Model IDs — kept up to date (March 2026)
_DEFAULT_CLAUDE_MODEL = "claude-sonnet-4-6"
_DEFAULT_OPENROUTER_MODEL = "openai/gpt-5.4-mini"

# Picker-ready model lists for the Gradio UI
CLAUDE_MODELS = [
    "claude-sonnet-4-6",
    "claude-opus-4-6",
    "claude-haiku-4-5-20251001",
]

OPENROUTER_MODELS = [
    "openai/gpt-5.4-mini",
    "openai/gpt-5.4-nano",
    "openai/gpt-5.4",
    "mistralai/mistral-small-2603",
    "x-ai/grok-4.20-beta",
    "minimax/minimax-m2.7",
    "nvidia/nemotron-3-super-120b-a12b:free",
]


# ── Helpers ────────────────────────────────────────────────────────────────────

def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 characters per token."""
    return max(1, len(text) // 4)


def _retry(fn, max_retries: int = None, base_delay: float = None):
    """Call fn with exponential backoff on failure. Raises last exception after all retries."""
    if max_retries is None:
        max_retries = MAX_RETRIES
    if base_delay is None:
        base_delay = RETRY_BASE_DELAY

    last_exc = None
    for attempt in range(max(1, max_retries)):
        try:
            return fn()
        except Exception as exc:
            last_exc = exc
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
    raise last_exc


# ── Signals builder ────────────────────────────────────────────────────────────

def build_signals_dict(include_notes: bool = True) -> dict:
    """Collect current signals from all sources."""
    signals = {
        "file_events": get_recent_file_events(limit=20, since_seconds=3600),
        "git_commits": get_recent_git_commits(limit=10),
        "terminal_commands": get_recent_terminal_commands(limit=50),
        "collected_at": time.time(),
    }
    if include_notes:
        try:
            from .meeting_notes import scan_meeting_notes
            signals["meeting_notes"] = scan_meeting_notes()
        except Exception:
            signals["meeting_notes"] = []
    else:
        signals["meeting_notes"] = []
    return signals


# ── Mock summariser ────────────────────────────────────────────────────────────

def generate_mock_summary(signals: dict) -> str:
    """Generate a plausible context summary without calling any LLM."""
    from .timeline import compute_confidence_score

    files = signals.get("file_events", [])
    commits = signals.get("git_commits", [])
    commands = signals.get("terminal_commands", [])
    notes = signals.get("meeting_notes", [])

    file_names = list(dict.fromkeys(Path(f["path"]).name for f in files))[:6]
    file_block = (
        "\n".join(f"- {n}" for n in file_names) if file_names else "- No recent file changes"
    )

    commit_block = (
        "\n".join(
            f"- `{c['hash']}` {c['message'][:55]} — {c['author'].split('<')[0].strip()}"
            for c in commits[:5]
        )
        if commits
        else "- No recent commits"
    )

    cmd_block = (
        "\n".join(f"- `{c['command'][:65]}`" for c in commands[:8])
        if commands
        else "- No recent commands"
    )

    # Infer work type
    py_files = [f for f in files if Path(f["path"]).suffix == ".py"]
    js_files = [f for f in files if Path(f["path"]).suffix in (".js", ".ts", ".tsx", ".jsx")]
    if py_files:
        activity = "Python development"
    elif js_files:
        activity = "JavaScript/TypeScript development"
    else:
        activity = "active development"

    has_tests = any("test" in c["command"].lower() for c in commands)
    has_git = any("git" in c["command"].lower() for c in commands)
    has_docker = any("docker" in c["command"].lower() for c in commands)

    confidence = compute_confidence_score(signals)

    notes_block = ""
    if notes:
        try:
            from .meeting_notes import format_notes_for_context
            nfmt = format_notes_for_context(notes)
            if nfmt:
                notes_block = f"\n\n{nfmt}"
        except Exception:
            pass

    collected_ts = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(signals.get("collected_at", time.time()))
    )

    summary = f"""## Current Developer Context
*Collected: {collected_ts} | Files: {len(files)}, Commits: {len(commits)}, Commands: {len(commands)}*

**Active Work:**
{file_block}

**Recent Git Commits:**
{commit_block}

**Recent Terminal Commands:**
{cmd_block}{notes_block}

**Context Summary:**
Developer is engaged in {activity}. \
{"Tests are being run regularly, indicating TDD or validation workflow. " if has_tests else ""}\
{"Git operations suggest active commit/push cycle. " if has_git else ""}\
{"Docker usage detected — containerised environment. " if has_docker else ""}\
{len(files)} file event(s) in the last hour, {len(commits)} commit(s), {len(commands)} commands tracked.

**Key Signals:**
- Modified files: {len(files)}
- Commits detected: {len(commits)}
- Commands tracked: {len(commands)}
- Meeting notes indexed: {len(notes)}
- Confidence score: {confidence}/100

*Mock mode — set ANTHROPIC_API_KEY or OPENROUTER_API_KEY for AI-powered compression*"""

    return summary


# ── Shared prompt builder ──────────────────────────────────────────────────────

def _build_prompt(signals: dict, max_tokens: int) -> str:
    files = signals.get("file_events", [])
    commits = signals.get("git_commits", [])
    commands = signals.get("terminal_commands", [])
    notes = signals.get("meeting_notes", [])

    from .timeline import compute_confidence_score
    confidence = compute_confidence_score(signals)

    collected_ts = time.strftime(
        "%Y-%m-%d %H:%M:%S", time.localtime(signals.get("collected_at", time.time()))
    )

    signals_text = (
        f"COLLECTED AT: {collected_ts}\n\n"
        f"FILE EVENTS (last hour, {len(files)} total):\n"
        + json.dumps(files[:15], indent=2, default=str)
        + f"\n\nGIT COMMITS (recent, {len(commits)} total):\n"
        + json.dumps(commits[:10], indent=2, default=str)
        + f"\n\nTERMINAL COMMANDS (recent, {len(commands)} total):\n"
        + json.dumps(commands[:25], indent=2, default=str)
    )
    if notes:
        signals_text += f"\n\nMEETING NOTES ({len(notes)} recent):\n" + json.dumps(
            notes[:5], indent=2, default=str
        )

    return f"""You are a developer context compressor. Analyse these activity signals and produce a structured context summary that can be pasted into any LLM prompt.

OUTPUT FORMAT (use exactly this structure):
## Current Developer Context
*Collected: <timestamp> | Files: N, Commits: N, Commands: N*

**Active Work:** (what files/features are being worked on right now)
**Recent Git Commits:** (key commit messages with hashes)
**Recent Terminal Commands:** (most interesting/relevant commands)
**Meeting Notes:** (if notes provided, summarise key topics; otherwise omit this section)
**Context Summary:** (2-3 sentences: what the developer is doing, patterns, key focus area)
**Key Signals:** (3-4 bullet points of actionable insights; include confidence: {confidence}/100)

RULES:
- Keep total output under {max_tokens} tokens
- Be specific and concrete, not generic
- Focus on what matters for continuing this work

SIGNALS:
{signals_text}"""


# ── Anthropic Claude summariser ────────────────────────────────────────────────

def compress_with_claude(signals: dict) -> str:
    """Call Claude (Anthropic API) to produce a structured context summary."""
    import anthropic

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    model = os.getenv("CLAUDE_MODEL", _DEFAULT_CLAUDE_MODEL)
    max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", "600"))

    prompt = _build_prompt(signals, max_tokens)
    client = anthropic.Anthropic(api_key=api_key)

    def _call():
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    return _retry(_call)


# ── OpenRouter summariser ──────────────────────────────────────────────────────

def compress_with_openrouter(signals: dict) -> str:
    """Call an OpenRouter model to produce a structured context summary."""
    import requests

    api_key = os.getenv("OPENROUTER_API_KEY", "")
    model = os.getenv("OPENROUTER_MODEL", _DEFAULT_OPENROUTER_MODEL)
    max_tokens = int(os.getenv("CONTEXT_MAX_TOKENS", "600"))

    prompt = _build_prompt(signals, max_tokens)
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://github.com/ambient-context-aggregator",
        "X-Title": "Ambient Context Aggregator",
    }
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }

    def _call():
        resp = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    return _retry(_call)


# ── Public API ─────────────────────────────────────────────────────────────────

def get_or_generate_context(force_refresh: bool = False, use_mock: bool = None) -> dict:
    """
    Return a context summary dict, using cache when possible.

    Returns:
        {
            "summary":            str,
            "token_estimate":     int,
            "signals":            dict,
            "created_at":         float,
            "generation_time_ms": int,
            "confidence":         float,
            "provider":           str,  # "anthropic" | "openrouter" | "mock"
        }
    """
    from .timeline import compute_confidence_score

    # Serve from cache when still fresh
    if not force_refresh:
        cached = get_latest_context_summary()
        if cached and (time.time() - cached["created_at"]) < CACHE_TTL:
            sigs = cached.get("signals", {})
            return {
                "summary": cached["summary"],
                "token_estimate": cached["token_estimate"],
                "signals": sigs,
                "created_at": cached["created_at"],
                "generation_time_ms": cached.get("generation_time_ms",0),
                "confidence": compute_confidence_score(sigs),
                "provider": cached.get("provider", "cache"),
            }

    signals = build_signals_dict()

    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "")
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "")

    if use_mock is None:
        use_mock = not bool(anthropic_key) and not bool(openrouter_key)

    provider = "mock"
    t0 = time.time()

    if use_mock:
        summary = generate_mock_summary(signals)
    elif anthropic_key:
        try:
            summary = compress_with_claude(signals)
            provider = "anthropic"
        except Exception as exc:
            if openrouter_key:
                try:
                    summary = compress_with_openrouter(signals)
                    provider = "openrouter"
                except Exception as exc2:
                    summary = generate_mock_summary(signals)
                    summary += f"\n\n*Note: LLM APIs unavailable ({exc}, {exc2}) — mock summary*"
            else:
                summary = generate_mock_summary(signals)
                summary += f"\n\n*Note: Claude API unavailable ({exc}) — mock summary*"
    else:
        try:
            summary = compress_with_openrouter(signals)
            provider = "openrouter"
        except Exception as exc:
            summary = generate_mock_summary(signals)
            summary += f"\n\n*Note: OpenRouter unavailable ({exc}) — mock summary*"

    generation_time_ms = int((time.time() - t0) * 1000)
    token_estimate = estimate_tokens(summary)
    confidence = compute_confidence_score(signals)

    save_context_summary(
        summary, token_estimate, signals,
        generation_time_ms=generation_time_ms,
        provider=provider,
    )

    return {
        "summary": summary,
        "token_estimate": token_estimate,
        "signals": signals,
        "created_at": time.time(),
        "generation_time_ms": generation_time_ms,
        "confidence": confidence,
        "provider": provider,
    }


def generate_context(context_hint: str = "", force_refresh: bool = False) -> tuple:
    """
    Generate context and return exactly 3 values for test compatibility.
    
    Returns:
        (ctx_text, status, token_text) tuple
    """
    result = get_or_generate_context(force_refresh=force_refresh, use_mock=True)
    ctx_text = result.get("summary", "")
    status = result.get("provider", "mock")
    token_text = f"~{result.get('token_estimate', 0)} tokens"
    return (ctx_text, status, token_text)
