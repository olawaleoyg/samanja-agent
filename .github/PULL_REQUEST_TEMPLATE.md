## What does this PR do?

<!-- One or two sentences describing the change. -->

## Why?

<!-- Link an issue, or explain the motivation. -->

## How was this tested?

- [ ] `pytest -v` passes locally
- [ ] Added/updated tests for this change
- [ ] Ran `pre-commit run --all-files`

## Security checklist (if touching `agent.py`, CI, or dependencies)

- [ ] No new command execution paths added outside `ALLOWED_COMMANDS`
- [ ] No new file access outside `PROJECT_ROOT` sandboxing
- [ ] No secrets committed (gitleaks passes)
- [ ] Dependency changes reviewed for known CVEs (pip-audit passes)

## Screenshots / logs (if relevant)

<!-- Optional -->
