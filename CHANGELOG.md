# Changelog

All notable changes to this project are documented in this file.

## [Unreleased] - Security Hardening

### Added
- Command allowlist for `run_shell_command` in `agent.py` - only `git`
  (status/log/diff/branch/rev-parse), `npm` (install/run/test/ci),
  `pytest`, and `ls` are permitted. Commands now execute as argv lists
  with `shell=False` instead of raw shell strings.
- Project-root path sandboxing for `read_file` in `agent.py` - all paths
  are resolved and verified to stay inside `PROJECT_ROOT` (configurable
  via `AGENT_PROJECT_ROOT`), bxlocking path traversal (`../../etc/passwd`)
  and arbitrary absolute-path reads.
- Security regression tests in `tests/test_agent.py` covering allowlist
  rejection, shell-injection attempts, path traversal, and an end-to-end
  rejection flow through `run_agent`.
- Gitleaks secret scanning:
  - New `secret-scan` job in CI (`.github/workflows/ci.yml`), running
    first and gating all downstream jobs.
  - New `gitleaks` pre-commit hook in `.pre-commit-config.yaml`,
    catching secrets before they're ever committed locally.
  - `.gitleaks.toml` config allowlisting `.env.example` and test
    fixtures to avoid false positives.
- Dependency vulnerability scanning:
  - New `dependency-audit` CI job running `pip-audit` against
    `requirements.txt` and `requirements-dev.txt`.
  - `.github/dependabot.yml` for weekly automated dependency PRs
    (Python packages + GitHub Actions versions), with minor/patch
    updates grouped to reduce PR noise.
- Bandit static security analysis (SAST) added to the `lint-and-fix`
  CI job, run against the full codebase (excluding `tests/`). This
  would have caught the original `shell=True` pattern automatically.

### Changed
- `GitHub Actions` workflow permissions scoped from a blanket
  `permissions: contents: write` at the workflow level down to
  least-privilege: `contents: read` by default, with `contents: write`
  granted only to the `lint-and-fix` job (the only job that commits
  auto-fixes back to a PR branch).
- CI job order updated to:
  `secret-scan` -> `dependency-audit` -> `lint-and-fix` -> `test` -> `pipeline`,
  each gated on the previous job passing.
- `README.md` updated with a new **Security model** section documenting
  the command allowlist, file sandboxing, and rationale, replacing the
  previous "no sandboxing, trust the directory" warning.

### Security
- Fixed: command injection risk in `run_shell_command` (arbitrary
  `shell=True` execution of model-supplied strings).
- Fixed: unrestricted file read in `read_file` (no path containment,
  allowed reads outside the project directory).
- Mitigated: risk of committed secrets going undetected (gitleaks).
- Mitigated: risk of running with known-vulnerable dependencies
  (pip-audit + Dependabot).
- Mitigated: overly broad CI token permissions (scoped per job).
- Mitigated: lack of automated static security review (bandit).
