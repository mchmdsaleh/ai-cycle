# ai-cycle

Multi-agent AI coding cycle orchestrator: Codex implements, Copilot and
Claude Code review adversarially, then deterministic validation runs.

## Install

```bash
cd /opt/project/ai-cycle
pipx install -e .
# or: pip install -e . --break-system-packages
```

## Usage

```bash
ai-cycle init              # scaffold .ai-cycle/ in the current repo
ai-cycle run                # run a fresh cycle
ai-cycle run --resume        # resume from the latest failed run
ai-cycle status              # show run history
ai-cycle logs <run-id>       # show details for one run
ai-cycle worktree add <name> [--base main]
ai-cycle worktree list
ai-cycle worktree remove <name>
```
