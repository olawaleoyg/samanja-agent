# devops-agent

A minimal Claude-powered agent that helps take a website from code to a
verified live deployment. Built as a first hands-on example of the
"agent loop" pattern: give Claude a goal and a small set of tools, and
let it decide which tools to call, in what order, until the goal is done.

## What it does

Given a plain-English goal (e.g. *"build this site and confirm it's
live"*), the agent can:

- Run allowlisted shell commands (`git status`, `npm run build`,
  `npm install`, `pytest`, `ls`) — see **Security model** below
- Check whether a URL is live and how fast it responds
- Read project files (e.g. `package.json`, config files) for context,
  restricted to the project directory

## Project structure

```
devops-agent/
├── agent.py              # the agent + tool definitions
├── requirements.txt      # runtime dependencies
├── requirements-dev.txt  # test/dev dependencies
├── tests/
│   └── test_agent.py     # unit tests (mocked, no real API/network calls)
├── docs/
│   └── ARCHITECTURE.md   # how the agent loop works, extension points
├── .env.example
├── .gitignore
├── CONTRIBUTING.md
├── CHANGELOG.md
└── LICENSE
```

## Setup

```bash
git clone <this-repo-url>
cd devops-agent
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your real ANTHROPIC_API_KEY
export $(cat .env | xargs)
```

## Usage

Edit the `goal` variable at the bottom of `agent.py`, then run:

```bash
python agent.py
```

Example goals:

```text
Check git status, then tell me if there are uncommitted changes.
```

```text
Run `npm run build`, then verify https://mysite.com returns a
200 status code.
```

## Running tests

```bash
pip install -r requirements-dev.txt
pytest -v
```

Tests mock all external calls (shell commands that would touch real
infra, HTTP requests, and the Anthropic API itself), so `pytest` is
safe to run in CI without secrets or network access. The suite also
includes security regression tests for the command allowlist and file
sandbox described below — see `tests/test_agent.py`.

## Pre-push checks (local)

This repo uses [pre-commit](https://pre-commit.com) to catch issues
before code ever reaches GitHub:

```bash
pip install -r requirements-dev.txt
pre-commit install --hook-type pre-commit --hook-type pre-push
```

After that:
- **On `git commit`** → Black and Ruff auto-format and auto-fix your code.
- **On `git push`** → the full `pytest` suite runs; the push is blocked
  if any test fails.

## CI/CD pipeline (GitHub Actions)

`.github/workflows/ci.yml` runs on every PR and on pushes to `main`,
in three gated stages:

1. **`lint-and-fix`** — runs Black + Ruff, auto-fixes what it safely
   can, commits the fixes back to the PR branch, then fails the job if
   anything remains that needs a human to fix.
2. **`test`** — runs the full `pytest` suite. Only runs if lint passed.
3. **`pipeline`** — your real build/deploy steps. Only runs on `main`,
   and only if both lint and tests passed.

So a broken or unformatted PR never reaches the deploy step — it gets
caught, and where possible auto-fixed, before the pipeline runs.

## Security model

`run_shell_command` and `read_file` are the two tools that touch the
real filesystem/shell, so both are locked down rather than left open:

- **Command allowlist, no shell interpolation.** `run_shell_command`
  takes a command as an argv list (e.g. `["git", "status"]`), never a
  raw string, and runs with `shell=False`. Only programs/subcommands in
  `ALLOWED_COMMANDS` inside `agent.py` are permitted (`git`
  status/log/diff/branch/rev-parse, `npm` install/run/test/ci, `pytest`,
  `ls`). Anything else — including shell metacharacters like `;`, `|`,
  or `&&` smuggled into a single string — is rejected before execution.
  Add deploy CLIs (`vercel`, `netlify`, etc.) to the allowlist only if
  you intentionally want the agent to be able to deploy.
- **Project-root file sandboxing.** `read_file` resolves every path
  with `Path.resolve()` and rejects anything that falls outside
  `PROJECT_ROOT` (defaults to the current working directory; override
  with the `AGENT_PROJECT_ROOT` environment variable). This blocks
  traversal attempts like `../../etc/passwd` and arbitrary absolute
  paths outside the project.
- **Why this matters:** Claude never touches your machine directly — it
  only requests tool calls by name, and the Python code decides what
  each tool is actually allowed to do (see `docs/ARCHITECTURE.md`). The
  allowlist and path sandbox are the enforcement point for that trust
  boundary.
- Only point this agent at projects/directories you trust, and start
  with read-only goals (`git status`, URL checks) before letting it run
  build commands.
- Treat your `ANTHROPIC_API_KEY` like any other secret — never commit
  `.env` (already covered by `.gitignore`).

## License

MIT — see [LICENSE](LICENSE).
