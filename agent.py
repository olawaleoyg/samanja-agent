"""
Simple DevOps / Web-Deploy Agent
=================================

A minimal example of an "agent": Claude is given a goal in plain English
(e.g. "build this site and check it's live"), and a small set of tools.
Claude decides WHICH tools to call and in WHAT order, in a loop, until
the goal is done. That loop is the whole trick.

Setup:
pip install anthropic requests
export ANTHROPIC_API_KEY="your-key-here"

Run:
python agent.py
"""

import os
import shlex
import subprocess
import requests
from pathlib import Path
from anthropic import Anthropic

client = Anthropic()  # reads ANTHROPIC_API_KEY from env
MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# 0. SECURITY CONFIG
# ---------------------------------------------------------------------------

# Only these top-level commands may ever be executed. Add deploy CLIs here
# only if you intentionally want the agent to be able to deploy.
ALLOWED_COMMANDS = {
    "git": {"status", "log", "diff", "branch", "rev-parse"},
    "npm": {"install", "run", "test", "ci"},
    "pytest": None,  # None = any subcommand/args allowed
    "ls": None,
}

# The project root that all file reads must stay inside.
PROJECT_ROOT = Path(os.environ.get("AGENT_PROJECT_ROOT", os.getcwd())).resolve()

MAX_FILE_BYTES = 4000
COMMAND_TIMEOUT_SECONDS = 120


class ToolSecurityError(Exception):
    """Raised when a tool call violates the security policy."""


# ---------------------------------------------------------------------------
# 1. TOOLS
# Each tool is (a) a JSON schema Claude sees, and (b) a Python function that
# actually does the work when Claude asks for it.
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "run_shell_command",
        "description": (
            "Run an allowlisted command in the project directory. Supported "
            "commands: git (status/log/diff/branch/rev-parse), npm "
            "(install/run/test/ci), pytest, ls. Pass the command and its "
            "arguments as a list, e.g. ['git', 'status']."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "The command and arguments as separate list items, e.g. ['npm', 'run', 'build']",
                }
            },
            "required": ["command"],
        },
    },
    {
        "name": "check_url_status",
        "description": "Check whether a URL is live and returns its HTTP status code and load time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "Full URL to check, e.g. https://example.com"}
            },
            "required": ["url"],
        },
    },
    {
        "name": "read_file",
        "description": "Read the contents of a file inside the project directory (e.g. package.json, README.md).",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Relative file path inside the project root"}
            },
            "required": ["path"],
        },
    },
]


def run_shell_command(command) -> str:
    """Run an allowlisted command. `command` must be a list of argv tokens
    (never a raw shell string), and is executed with shell=False."""
    try:
        if isinstance(command, str):
            # Defensive: if a string slips through, parse it safely rather
            # than handing it to the shell.
            argv = shlex.split(command)
        else:
            argv = list(command)

        if not argv:
            return "Error: empty command"

        program = argv[0]
        if program not in ALLOWED_COMMANDS:
            return f"Error: command '{program}' is not in the allowlist"

        allowed_subcommands = ALLOWED_COMMANDS[program]
        if allowed_subcommands is not None and len(argv) > 1:
            if argv[1] not in allowed_subcommands:
                return f"Error: '{program} {argv[1]}' is not in the allowlist"

        result = subprocess.run(
            argv,
            shell=False,
            capture_output=True,
            text=True,
            timeout=COMMAND_TIMEOUT_SECONDS,
            cwd=str(PROJECT_ROOT),
        )
        output = result.stdout + result.stderr
        return output.strip()[:MAX_FILE_BYTES] or "(command produced no output)"
    except subprocess.TimeoutExpired:
        return "Error: command timed out"
    except Exception as e:
        return f"Error running command: {e}"


def check_url_status(url: str) -> str:
    try:
        r = requests.get(url, timeout=10)
        return f"status={r.status_code}, load_time={r.elapsed.total_seconds():.2f}s"
    except Exception as e:
        return f"Error reaching {url}: {e}"


def _resolve_safe_path(path: str) -> Path:
    """Resolve `path` and ensure it stays inside PROJECT_ROOT. Raises
    ToolSecurityError if the resolved path escapes the project root."""
    candidate = (PROJECT_ROOT / path).resolve() if not os.path.isabs(path) else Path(path).resolve()
    try:
        candidate.relative_to(PROJECT_ROOT)
    except ValueError:
        raise ToolSecurityError(
            f"Path '{path}' resolves outside the project root ({PROJECT_ROOT})"
        )
    return candidate


def read_file(path: str) -> str:
    try:
        safe_path = _resolve_safe_path(path)
        if not safe_path.is_file():
            return f"Error reading file: '{path}' is not a file"
        with open(safe_path, "r", errors="replace") as f:
            return f.read()[:MAX_FILE_BYTES]
    except ToolSecurityError as e:
        return f"Error: {e}"
    except Exception as e:
        return f"Error reading file: {e}"


TOOL_FUNCTIONS = {
    "run_shell_command": run_shell_command,
    "check_url_status": check_url_status,
    "read_file": read_file,
}

# ---------------------------------------------------------------------------
# 2. THE AGENT LOOP
# ---------------------------------------------------------------------------


def run_agent(goal: str, max_turns: int = 10):
    messages = [{"role": "user", "content": goal}]
    system_prompt = (
        "You are a DevOps assistant that helps a web developer take a site "
        "from code to a live, verified deployment. Use the available tools "
        "to inspect the project, run builds, deploy, and confirm the live "
        "URL is actually reachable. Tool calls are restricted to an "
        "allowlist and a project-root file sandbox; if a tool is rejected, "
        "explain why rather than retrying with a workaround. Be concise. "
        "Stop once the goal is verified or you hit a blocker you can't "
        "resolve, and explain clearly what happened."
    )

    for turn in range(max_turns):
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        for block in response.content:
            if block.type == "text":
                print(f"\n[agent] {block.text}")

        if response.stop_reason != "tool_use":
            break  # Claude is done — no more tools to call

        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                fn = TOOL_FUNCTIONS.get(block.name)
                print(f"[tool call] {block.name}({block.input})")
                result = fn(**block.input) if fn else "Unknown tool"
                print(f"[tool result] {result[:300]}")
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    }
                )
        messages.append({"role": "user", "content": tool_results})
    else:
        print("\n[agent] Hit max turns without finishing.")


if __name__ == "__main__":
    # Example goal — edit this to match your actual project/site.
    goal = (
        "In the current directory, check git status, run `npm run build` "
        "if there's a package.json, then check whether https://example.com "
        "is live and report its status."
    )
    run_agent(goal)
