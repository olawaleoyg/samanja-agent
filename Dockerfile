# syntax=docker/dockerfile:1

# -----------------------------------------------------------------------
# devops-agent Dockerfile
#
# Built as a ONE-SHOT CLI container: it runs `python agent.py` for a
# single goal, then exits. This matches the current agent.py design
# (run_agent(goal) executes once and returns).
#
# >>> MODIFY HERE if your use case changes <<<
# If you later wrap this agent in a long-lived service (e.g. a FastAPI/
# Flask server that accepts goals over HTTP, or a scheduler that polls
# for jobs), change the CMD at the bottom from running agent.py directly
# to starting that server process instead, and add a HEALTHCHECK
# instruction (see commented example below) plus an EXPOSE for its port.
# -----------------------------------------------------------------------

# Best practice: pin an exact minor version, use -slim for smaller attack
# surface than the full image, avoid `latest`.
FROM python:3.11-slim AS base

# Best practice: run as non-root.
RUN useradd --create-home --uid 1000 agent
WORKDIR /home/agent/app

# Install dependencies first (better layer caching -- only re-runs pip
# install if requirements.txt actually changes, not on every code edit).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# >>> MODIFY HERE if you need dev tools (pytest, black, ruff, bandit)
# inside the image too, e.g. for a CI container:
# COPY requirements-dev.txt .
# RUN pip install --no-cache-dir -r requirements-dev.txt

COPY --chown=agent:agent agent.py .

# Drop root privileges before running application code.
USER agent

# Security-relevant environment variables should be passed at `docker run`
# time (-e ANTHROPIC_API_KEY=...) or via a secrets manager -- never baked
# into the image with ENV or COPY of a real .env file.
ENV PYTHONUNBUFFERED=1

# >>> MODIFY HERE if this becomes a long-lived service <<<
# Example of what a long-running variant would add instead of the CMD below:
#   EXPOSE 8080
#   HEALTHCHECK --interval=30s --timeout=5s --start-period=10s \
#     CMD curl -f http://localhost:8080/health || exit 1
#   CMD ["python", "server.py"]

# One-shot CLI entrypoint: runs the agent once and exits.
# Override the goal via `docker run <image> python agent.py "your goal here"`
# if you parameterize agent.py to accept argv instead of a hardcoded goal.
CMD ["python", "agent.py"]
