# Security Policy

## Supported Versions

This project is currently pre-1.0 and does not maintain multiple
supported release branches. Security fixes are applied to `main` only.

## Reporting a Vulnerability

If you discover a security vulnerability in this project (e.g. a bypass
of the command allowlist in `run_shell_command`, a path traversal in
`read_file`, or a secret exposure), please report it privately rather
than opening a public issue.

- Email: security@your-domain.example (replace with a real contact)
- Please include: a description of the issue, steps to reproduce, and
  the potential impact.
- We aim to acknowledge reports within 3 business days and provide a
  fix or mitigation timeline within 14 days for confirmed issues.

## Scope

In scope:
- Command injection or allowlist bypass in `agent.py`
- Path traversal or file sandbox bypass
- Secrets leaking through logs, CI, or committed files
- Dependency vulnerabilities not caught by `pip-audit`/Dependabot

Out of scope:
- Issues requiring a compromised `ANTHROPIC_API_KEY` or local machine
  access the attacker already has
- Denial of service via excessive legitimate API usage (see token/time
  ceilings in `agent.py` for existing mitigations)

## Disclosure

Please give us a reasonable window to fix confirmed issues before any
public disclosure. Credit will be given in `CHANGELOG.md` unless you
prefer to remain anonymous.
