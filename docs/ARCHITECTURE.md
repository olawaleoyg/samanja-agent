# Architecture

## The agent loop

This project's core idea is a loop, not a single request/response:

1. The user gives a goal in plain English (e.g. "build and deploy this site").
2. Claude is sent the goal plus a list of available **tools** (schemas only —
   no actual code is sent to Claude).
3. Claude replies with either:
   - plain text (it's done, or it's stuck), or
   - one or more `tool_use` requests (it wants to run something).
4. If Claude requested tools, the Python code actually executes them
   (`run_shell_command`, `check_url_status`, `read_file`) and sends the
   real-world result back to Claude as a `tool_result`.
5. Claude sees the result and decides the next step — repeat from step 3.
6. The loop ends when Claude stops requesting tools, `max_turns` is hit,
   the token/time cost ceiling is exceeded, or the Anthropic API call
   fails after exhausting retries.

```
 user goal
    │
    ▼
┌─────────────┐      tool_use       ┌──────────────────┐
│   Claude    │ ─────────────────▶  │  Python executes  │
│ (decides    │                     │  the real tool     │
│  next step) │ ◀───────────────── │  (shell/HTTP/file) │
└─────────────┘     tool_result     └──────────────────┘
    │
    ▼ (no more tool_use)
 final answer to user
```

## Why this matters

Claude never directly touches your machine. It can only ever request a
tool call by name — the Python code you control decides what that tool
actually does and what it's allowed to access. This is the whole trust
boundary, and it is actively enforced today, not just a future option:

- **`run_shell_command`** only executes commands present in the
  `ALLOWED_COMMANDS` allowlist (`git` status/log/diff/branch/rev-parse,
  `npm` install/run/test/ci, `pytest`, `ls`), passed as an argv list and
  run with `shell=False` — never a raw shell string. Anything outside
  the allowlist, including shell metacharacters smuggled into a single
  string, is rejected before execution.
- **`read_file`** resolves every path with `Path.resolve()` and rejects
  anything outside `PROJECT_ROOT` (configurable via `AGENT_PROJECT_ROOT`),
  blocking path traversal (`../../etc/passwd`) and arbitrary absolute
  paths.
- **API calls** use the Anthropic SDK's built-in `max_retries` for
  exponential backoff on transient 429/5xx/connection errors, so a
  single flaky response doesn't kill the whole run.
- **Cost ceilings** (`MAX_TOTAL_TOKENS`, `MAX_RUN_SECONDS`) cap total
  token spend and wall-clock time per run, aborting cleanly if either
  is exceeded — protection against a runaway loop.
- **Structured JSON logging** records every tool request, rejection,
  retry, and cost-ceiling event, so runs are debuggable in CI logs or a
  log aggregator instead of relying on `print()` output.

You can still tighten this further — e.g. sandboxing `run_shell_command`
in a container, or adding approval prompts before destructive commands
— but the baseline enforcement described above is already live in
`agent.py`, not just a design intention.

## Extension points

- **New tools**: add an entry to the `TOOLS` list (JSON schema) and a
  matching function in `TOOL_FUNCTIONS`. If the tool touches the
  filesystem or shell, route it through `_resolve_safe_path()` or add
  it to `ALLOWED_COMMANDS` — don't bypass the existing guards.
- **Approval gating**: wrap tool execution in a confirmation step before
  running anything destructive (e.g. deploy commands). Not yet
  implemented — the allowlist currently excludes deploy CLIs by default
  for this reason; add them deliberately if you want the agent to
  deploy unattended.
- **Structured logging**: already implemented via Python's `logging`
  module with a JSON formatter (see `agent.py`) — extend it by adding
  more `extra={...}` fields per event rather than introducing a new
  logging approach.
- **Multiple agents**: this single-agent loop can be composed into a
  pipeline (e.g. a "build agent" hands off to a "verify agent").
- **CI/CD hardening**: secret scanning (gitleaks), dependency auditing
  (pip-audit + Dependabot), SAST (bandit), and a coverage-gated test
  matrix are already wired into `.github/workflows/ci.yml` — see
  `README.md` for the full pipeline order and how to test each piece.
