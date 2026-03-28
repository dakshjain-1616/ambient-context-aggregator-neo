# Ambient Context Aggregator – Passive dev-context snapshot for any LLM

> *Made autonomously using [NEO](https://heyneo.so) · [![Install NEO Extension](https://img.shields.io/badge/VS%20Code-Install%20NEO-7B61FF?logo=visual-studio-code)](https://marketplace.visualstudio.com/items?itemName=NeoResearchInc.heyneo)*

[![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Tests](https://img.shields.io/badge/tests-93%20passed-brightgreen.svg)]()

> Stop re-explaining your codebase to LLMs; this tool automatically builds a structured context window from your terminal history, open files, and git commits.

## Install

```bash
git clone https://github.com/dakshjain-1616/ambient-context-aggregator
cd ambient-context-aggregator
pip install -r requirements.txt
```

## What problem this solves

When you open a new VS Code Copilot Chat or a fresh Claude session mid-debug, you waste the first minute re-explaining the state of your application. You have to manually type: *"I'm in the `auth` module, I just fixed a 500 error in `login.py`, and I'm seeing a 403 on the refresh token."* Without a tool to capture this, you lose the context the moment you switch tabs. Existing solutions require manual tagging or maintaining a `CONTEXT.md` file by hand. `ambient-context-aggregator` fixes this by passively watching your terminal history (`.bash_history`), file system changes (via `watchdog`), and `git` logs to automatically generate a structured, LLM-ready context block.

## Real world examples

```bash
# Get the current context snapshot to clipboard
python -m ambient_context get
# Output: Context copied to clipboard. Ready for pasting into LLM.

# Start the local API server to serve context to other tools
python -m ambient_context serve
# Output: Running on http://127.0.0.1:8000 (Press CTRL+C to quit)
```

```python
# Programmatically ingest context into your own pipeline
from ambient_context.compressor import ContextCompressor
from ambient_context.git_scraper import GitScraper

scraper = GitScraper()
commits = scraper.get_recent_commits(hours=2)
compressor = ContextCompressor(commits)
context = compressor.summarize()
print(context)
```

## Who it's for

Backend and full-stack developers who rely on AI pair programmers (Copilot, Cursor, Claude) but frequently switch between unrelated tasks or branches. If you find yourself typing "Here is the context..." before every prompt, this tool automates that manual labor by keeping a live pulse on your local development environment.

## Quickstart

```bash
# Start the background watcher
python -m ambient_context watch

# Retrieve the latest summary
python -m ambient_context get
```

## Key features

- **Passive File Watching:** Uses `watchdog` to track opened files and edits without manual tagging.
- **Terminal History Parsing:** Reads `.bash_history` / `.zsh_history` to understand recent commands and errors.
- **Git Integration:** Scrapes recent commits via `gitpython` to identify active modules.
- **LLM Compression:** Summarizes raw signals into a structured context window using Anthropic API.
- **Multi-Interface:** Access via CLI, REST API (FastAPI), or Gradio Dashboard.

## Run tests

```bash
============================= test session starts ==============================
collected 93 items

tests/test_all.py ...................................................... [ 58%]
.......................................                                  [100%]

=============================== warnings summary ===============================
tests/test_all.py::TestGradioDashboard::test_get_dashboard_data_returns_5_panels
  /usr/local/lib/python3.12/dist-packages/gradio/routes.py:63: PendingDeprecationWarning: Please use `import python_multipart` instead.
    from multipart.multipart import parse_options_header

tests/test_all.py::TestGradioDashboard::test_build_interface_returns_blocks
  /usr/local/lib/python3.12/dist-packages/gradio/utils.py:98: DeprecationWarning: There is no current event loop
    asyncio.get_event_loop()

tests/test_all.py::TestGradioDashboard::test_build_interface_returns_blocks
tests/test_all.py::TestGradioDashboard::test_build_interface_returns_blocks
  /usr/local/lib/python3.12/dist-packages/gradio/routes.py:1215: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    @app.on_event("startup")

tests/test_all.py::TestGradioDashboard::test_build_interface_returns_blocks
tests/test_all.py::TestGradioDashboard::test_build_interface_returns_blocks
  /usr/local/lib/python3.12/dist-packages/fastapi/applications.py:4599: DeprecationWarning: 
          on_event is deprecated, use lifespan event handlers instead.
  
          Read more about it in the
          [FastAPI docs for Lifespan Events](https://fastapi.tiangolo.com/advanced/events/).
          
    return self.router.on_event(event_type)

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
======================= 93 passed, 6 warnings in 28.51s ========================
```

## Project structure

```
ambient-context-aggregator/
├── ambient_context/      ← main library
├── tests/                ← test suite
├── scripts/              ← demo scripts
└── requirements.txt
```