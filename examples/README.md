# Examples

Runnable scripts that demonstrate different features of the Ambient Context Aggregator.
Each script is self-contained and works from any directory — no API key required unless noted.

## Running an example

```bash
# From the project root
python examples/01_quick_start.py

# Or from within the examples/ directory
python 01_quick_start.py
```

## Scripts

| Script | What it demonstrates |
|--------|----------------------|
| [`01_quick_start.py`](01_quick_start.py) | Minimal working example: init DB, insert signals, generate a mock context summary (~15 lines of user code) |
| [`02_advanced_usage.py`](02_advanced_usage.py) | Query individual signal streams, inspect the hourly activity timeline, run the confidence scorer and focus analyser |
| [`03_custom_config.py`](03_custom_config.py) | Tune every major behaviour (DB path, model, token budget, cache TTL, history limits) via environment variables before importing |
| [`04_full_pipeline.py`](04_full_pipeline.py) | End-to-end workflow: start file watcher → inject signals → compress context → compute diff between snapshots → export markdown + JSON |

## Environment variables used in examples

| Variable | Default | Description |
|----------|---------|-------------|
| `DB_PATH` | `~/.ambient_context/context.db` | SQLite database path |
| `ANTHROPIC_API_KEY` | *(unset)* | Enable Claude-powered summaries |
| `OPENROUTER_API_KEY` | *(unset)* | Enable OpenRouter fallback |
| `CLAUDE_MODEL` | `claude-sonnet-4-6` | Claude model to use |
| `CONTEXT_MAX_TOKENS` | `600` | Max tokens in generated summary |
| `CONTEXT_CACHE_TTL` | `300` | Cache duration in seconds |
| `MAX_COMMITS` | `10` | Git commits to scrape |
| `MAX_HISTORY_LINES` | `100` | Shell history lines to read |

See `.env.example` in the project root for the full list.
