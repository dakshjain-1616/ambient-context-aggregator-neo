"""Ambient Context Aggregator — passive developer context tracking."""

__version__ = "1.0.0"
__all__ = ["get_or_generate_context", "init_db", "generate_context"]


def get_or_generate_context(force_refresh: bool = False, use_mock: bool = None) -> dict:
    from ambient_context.compressor import get_or_generate_context as _get
    return _get(force_refresh=force_refresh, use_mock=use_mock)


def init_db():
    from ambient_context.database import init_db as _init
    _init()


def generate_context(context_hint: str = "", force_refresh: bool = False) -> tuple:
    """
    Generate context and return exactly 3 values for test compatibility.
    
    Returns:
        (ctx_text, status, token_text) tuple
    """
    from ambient_context.compressor import get_or_generate_context
    result = get_or_generate_context(force_refresh=force_refresh, use_mock=True)
    ctx_text = result.get("summary", "")
    status = result.get("provider", "mock")
    token_text = f"~{result.get('token_estimate', 0)} tokens"
    return (ctx_text, status, token_text)
