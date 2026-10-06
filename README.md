# ai-cycle

Multi-agent AI coding cycle orchestrator: Codex implements, deterministic
validation runs, then Claude Code reviews.

## Install

```bash
cd /opt/project/ai-cycle
pipx install -e .
# or: pip install -e . --break-system-packages
```

## Usage

```bash
ai-cycle init              # scaffold .ai-cycle/ in the current repo
ai-cycle spec "Build hierarchical subtasks"
ai-cycle spec --input ./docs/wireframe.pdf
ai-cycle run                # run a fresh cycle
ai-cycle run --resume        # resume from the latest failed run
ai-cycle status              # show run history
ai-cycle logs <run-id>       # show details for one run
ai-cycle worktree add <name> [--base main]
ai-cycle worktree list
ai-cycle worktree remove <name>
```

Set `"review_model"` in `.ai-cycle/config.json` or `AI_CYCLE_REVIEW_MODEL`
to choose the Claude reviewer model (the environment variable takes priority).

By default the reviewer sees only uncommitted changes against `HEAD`. Set
`"base_branch"` only when the reviewer must also inspect committed branch
history. Review diffs larger than 1 MB stop before calling Claude.

The progress display refreshes while agents run and shows elapsed time, the
active log path, and its latest output. Logs are written as subprocesses emit
output; Claude print mode may stay silent until its answer is complete.
Use `tail -f <log-path>` in another terminal to follow a log directly.

Run artifacts under `.ai-cycle/` are excluded from the review diff.
Postmortem rule proposals are disabled by default to avoid an extra agent call
after failure. Set `"postmortem": true` in `.ai-cycle/config.json` to enable them.
