# 🦚 Danphe: Agentic Dev CLI & Social Automation

Danphe is a multi-purpose agentic tool that brings LLM-powered assistance directly to the terminal. It combines developer productivity tools (file editing, shell execution, code search) with social media automation (Instagram/WhatsApp).

## Project Overview

*   **Main Goal:** Provide a seamless, agentic interface for development tasks and social media interaction.
*   **Technologies:** Python 3.11+, Playwright (browser automation), NVIDIA NIM (primary LLM backend), Google Gemini (fallback LLM).
*   **Architecture:**
    *   **REPL/CLI:** Built with `click` and `prompt_toolkit` for interactive and one-off usage.
    *   **Agentic Loop:** Processes user intent, manages tool calling, and iterates until the task is complete.
    *   **Tooling:** Local file I/O, bash command execution, and code searching via `grep`.
    *   **Social Automation:** Uses persistent browser sessions (Playwright) to automate messaging on Instagram and WhatsApp.
    *   **LLM Routing:** Automatically selects the best model (NVIDIA or Gemini) based on token count and availability.

## Building and Running

### Prerequisites
*   Python 3.11 or higher.
*   Playwright browsers (Chromium for devloop/Gemini, Firefox for messaging).
*   Optional: Brave Browser (recommended for `devloop` integration).

### Installation
```bash
# Clone the repository
git clone <repo_url> danphe
cd danphe

# Set up virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Install Playwright browsers
playwright install chromium firefox
```

### Key Commands

*   **Interactive REPL:** `danphe` (or `python -m danphe.cli`)
*   **Single Question:** `danphe ask "How do I fix this bug?"`
*   **Agentic Task:** `danphe run "refactor the parser to use async"`
*   **Social Automation:** `danphe social instagram @username --auto-reply`
*   **Show Models:** `danphe models`

## Key Workflows

### 🤖 Agentic Developer Assistance
The `danphe run` command initiates an agentic loop. The agent can:
1.  **Read files:** Explore the codebase to understand the problem.
2.  **Search code:** Find relevant snippets using `search_code`.
3.  **Run bash:** Execute tests, build scripts, or git commands.
4.  **Write files:** Apply fixes or create new files.
5.  **Self-Correct:** Iterate based on command output (e.g., fixing a failing test).

### 📱 Social Media Automation
Danphe automates messaging platforms while maintaining human-like behavior:
*   **Session Persistence:** Saves browser profiles to `browser_data/` to avoid repeated logins.
*   **Auto-Reply:** Uses LLMs to generate context-aware, personality-driven replies.
*   **Continuous Mode:** Can watch a conversation and reply in real-time.
*   **Commands:** Use `/instagram` in the REPL or `danphe social` from the CLI.

## Development Conventions

*   **Project Context (`CLAUDE.md`):** Every prompt includes content from `CLAUDE.md` found in the project root. Use this file to define project-specific rules, tech stacks, and architecture.
*   **Skills:** Instructional markdown files located in `~/.danphe/skills/*.md` provide the agent with specialized knowledge. Use `list_skills` and `read_skill` to access them.
*   **Type Safety:** The project uses type hints extensively.
*   **UI:** Uses the `rich` library for formatted terminal output, including Markdown rendering and animated "thinking" states.
*   **Patches:** Code modifications are often extracted from LLM responses using specific markers like `# FILE: path`.

## Environment Variables

Configure Danphe by creating a `.env` file in the project root or `~/.danphe/.env`:

| Variable | Description |
| :--- | :--- |
| `NVIDIA_API_KEY` | API key for NVIDIA NIM models. |
| `GEMINI_API_KEY` | API key for Google Gemini models. |
| `DANPHE_MODEL` | Force a specific model tier (`fast`, `long`, `reasoning`, `gemini`). |
| `DANPHE_MAX_TOKENS` | Maximum output tokens for LLM responses. |
| `DANPHE_DEBUG` | Enable verbose logging (`true` / `false`). |

## Available Tools

The agent can call several built-in tools:
*   `read_file(path)`: Reads full file content.
*   `write_file(path, content)`: Writes content and creates backups.
*   `run_bash(command)`: Executes shell commands with a 30s timeout.
*   `list_files(path, pattern)`: Lists directory contents with glob filtering.
*   `search_code(pattern, path)`: Recursive grep search in source files.
*   `list_skills()`: Lists available skills in `~/.danphe/skills/`.
*   `read_skill(name)`: Reads full skill documentation.
