# Danphe project

## What this is
Danphe is an agentic developer CLI. It reads files, runs shell commands,
and applies patches — powered by NVIDIA NIM free models with Groq for fast turns.

## Stack
- Python 3.11+
- NVIDIA NIM API (OpenAI-compatible) — primary LLM backend
- Groq (Llama 3.3 70b) — fast path for small conversations
- Rich — terminal formatting
- Click — CLI framework

## Model routing
- Groq: fast tool-calling for small convos (< 12K tokens)
- glm-5.2: fast tasks, tool-calling (< 6K tokens)
- deepseek-v4-flash: long context, coding (< 60K tokens)
- nemotron-super: heavy reasoning (any size)

## Project layout
- danphe/cli.py      — REPL + Click entry point
- danphe/agent.py    — agentic loop
- danphe/router.py   — model routing
- danphe/patches.py  — extract + apply patches (ported from devloop)
- danphe/config.py   — env + CLAUDE.md loader
- danphe/llm/        — nvidia.py, groq.py, retry.py
- tools/             — file_tool.py, shell_tool.py
- plugins/           — instagram, devloop bridge (future)

## Coding conventions
- Type hints everywhere
- No Flask, no HTTP server — pure CLI
- Streaming by default
- Patches use ```python # FILE: path format
- Bash commands use ```bash format
