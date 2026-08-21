from __future__ import annotations

from pathlib import Path

from ai_cycle.core.runner import die, run


def git(*args, cwd=None, check=True):
    return run(["git", *args], cwd=cwd, check=check)


def assert_git_repo(root: Path):
    p = git("rev-parse", "--show-toplevel", cwd=root)
    repo = Path(p.stdout.strip()).resolve()
    if repo != root.resolve():
        die(f"Run this from repo root: {repo}")


def assert_clean_worktree(root: Path, allow_dirty: bool = False):
    if allow_dirty:
        return
    out = git("status", "--porcelain", cwd=root).stdout.strip()
    if out:
        die(
            "Working tree is not clean. Commit/stash existing changes first, "
            "or pass --allow-dirty if you intentionally want to include them."
        )


def current_branch(root: Path) -> str:
    return git("rev-parse", "--abbrev-ref", "HEAD", cwd=root).stdout.strip()


def get_diff(root: Path) -> str:
    base_branch = "origin/main"
    if git("rev-parse", "--verify", "origin/main", cwd=root, check=False).returncode != 0:
        base_branch = "main"

    chunks = []

    base_diff = run(["git", "diff", base_branch, "--no-ext-diff", "--binary"], cwd=root).stdout
    if base_diff.strip():
        chunks.append(base_diff)

    untracked_files = run(
        ["git", "ls-files", "--others", "--exclude-standard"], cwd=root
    ).stdout.splitlines()

    for rel_path in untracked_files:
        rel_path = rel_path.strip()
        if not rel_path:
            continue
        p = run(["git", "diff", "--no-index", "--binary", "--", "/dev/null", rel_path], cwd=root)
        if p.returncode not in (0, 1):
            die(f"Failed to generate diff for untracked file: {rel_path}")
        if p.stdout.strip():
            chunks.append(p.stdout)

    text = "\n".join(chunks)
    if not text.strip():
        die("Implementer produced no changes and no diff found against base branch.")
    return text


def worktrees_root(repo_root: Path) -> Path:
    return repo_root.parent / f"{repo_root.name}-worktrees"


def worktree_add(repo_root: Path, name: str, base: str = "main", existing: bool = False) -> Path:
    target = worktrees_root(repo_root) / name
    if target.exists():
        die(f"Worktree path already exists: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)

    if existing:
        args = ["worktree", "add", str(target), name]
    else:
        args = ["worktree", "add", "-b", name, str(target), base]

    p = git(*args, cwd=repo_root, check=False)
    if p.returncode != 0:
        die(f"git worktree add failed:\n{p.stdout}")
    return target


def worktree_list(repo_root: Path) -> list[dict]:
    p = git("worktree", "list", "--porcelain", cwd=repo_root)
    entries: list[dict] = []
    current: dict = {}
    for line in p.stdout.splitlines():
        if not line.strip():
            if current:
                entries.append(current)
                current = {}
            continue
        if line.startswith("worktree "):
            current["path"] = line[len("worktree "):].strip()
        elif line.startswith("branch "):
            current["branch"] = line[len("branch "):].strip().replace("refs/heads/", "")
        elif line == "bare":
            current["bare"] = True
        elif line == "detached":
            current["branch"] = "(detached)"
    if current:
        entries.append(current)
    return entries


def worktree_remove(repo_root: Path, path: Path, force: bool = False):
    args = ["worktree", "remove", str(path)]
    if force:
        args.append("--force")
    p = git(*args, cwd=repo_root, check=False)
    if p.returncode != 0:
        die(f"git worktree remove failed:\n{p.stdout}")
