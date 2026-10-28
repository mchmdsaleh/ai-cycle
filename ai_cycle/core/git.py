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


def resolve_base_branch(root: Path, base_branch: str | None = None) -> str:
    """Resolve the branch to diff against: explicit config value takes
    priority. Otherwise fall back to origin/main, then main. Set
    "base_branch" in .ai-cycle/config.json for repos whose integration
    branch isn't main (e.g. "development")."""
    candidates = [base_branch] if base_branch else []
    candidates += ["origin/main", "main"]

    for candidate in candidates:
        if not candidate:
            continue
        ref = candidate
        if "/" not in ref and git("rev-parse", "--verify", f"origin/{ref}", cwd=root, check=False).returncode == 0:
            ref = f"origin/{ref}"
        if git("rev-parse", "--verify", ref, cwd=root, check=False).returncode == 0:
            return ref

    die(f"Could not resolve a base branch to diff against (tried: {candidates}).")


def get_diff(root: Path, base_branch: str | None = None, *, allow_empty: bool = False) -> str:
    diff_base = "HEAD"
    if base_branch:
        base_ref = resolve_base_branch(root, base_branch)
        merge_base = git("merge-base", "HEAD", base_ref, cwd=root, check=False).stdout.strip()
        diff_base = merge_base or base_ref

    chunks = []

    paths = ["--", ".", ":(top,exclude).ai-cycle"]
    base_diff = run(["git", "diff", diff_base, "--no-ext-diff", "--binary", *paths], cwd=root).stdout
    if base_diff.strip():
        chunks.append(base_diff)

    untracked_files = run(
        ["git", "ls-files", "--others", "--exclude-standard", *paths], cwd=root
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
    if not text.strip() and not allow_empty:
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
