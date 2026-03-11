from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .models import DEFAULT_WORKSPACE_DIRNAME, DEFAULT_WORKTREES_DIRNAME, GitConfig, WorkflowError

CHECKPOINT_ENV = {
    "GIT_AUTHOR_NAME": "maker-checker",
    "GIT_AUTHOR_EMAIL": "maker-checker@example.com",
    "GIT_COMMITTER_NAME": "maker-checker",
    "GIT_COMMITTER_EMAIL": "maker-checker@example.com",
}


@dataclass
class GitRunContext:
    mode: str
    repo_root: Path
    base_ref: str
    base_commit: str
    cwd: Path
    branch: str | None = None
    worktree_path: Path | None = None
    current_checkpoint: str | None = None
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    rollbacks: list[dict[str, Any]] = field(default_factory=list)


def run_git(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=merged_env,
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        stderr = proc.stderr.strip() or proc.stdout.strip() or "git command failed"
        raise WorkflowError(f"git {' '.join(args)!r} failed in {cwd}: {stderr}")
    return proc.stdout.strip()


def resolve_repo_root(project_dir: Path) -> Path:
    output = run_git(["rev-parse", "--show-toplevel"], cwd=project_dir)
    return Path(output).resolve()


def resolve_commit(project_dir: Path, ref: str) -> str:
    return run_git(["rev-parse", ref], cwd=project_dir).strip()


def sanitize_branch_suffix(value: str) -> str:
    sanitized = re.sub(r"[^A-Za-z0-9._/-]+", "-", value).strip("-")
    return sanitized or "run"


def create_run_context(project_dir: Path, git_config: GitConfig, run_id: str) -> GitRunContext:
    repo_root = resolve_repo_root(project_dir)
    base_commit = resolve_commit(repo_root, git_config.base_ref)

    if git_config.mode == "inplace":
        return GitRunContext(
            mode="inplace",
            repo_root=repo_root,
            base_ref=git_config.base_ref,
            base_commit=base_commit,
            cwd=project_dir.resolve(),
            current_checkpoint=base_commit,
        )

    worktrees_dir = git_config.worktrees_dir
    if worktrees_dir is None:
        worktrees_dir = project_dir.resolve() / DEFAULT_WORKSPACE_DIRNAME / DEFAULT_WORKTREES_DIRNAME
    worktrees_dir = worktrees_dir.expanduser().resolve()
    worktrees_dir.mkdir(parents=True, exist_ok=True)
    worktree_path = worktrees_dir / run_id
    branch = f"maker-checker/{sanitize_branch_suffix(run_id)}"
    run_git(["worktree", "add", "-b", branch, str(worktree_path), base_commit], cwd=repo_root)
    return GitRunContext(
        mode="worktree",
        repo_root=repo_root,
        base_ref=git_config.base_ref,
        base_commit=base_commit,
        cwd=worktree_path,
        branch=branch,
        worktree_path=worktree_path,
        current_checkpoint=base_commit,
    )


def create_checkpoint(context: GitRunContext, label: str) -> str:
    run_git(["add", "-A"], cwd=context.cwd)
    run_git(
        ["commit", "--allow-empty", "-m", f"maker-checker checkpoint: {label}"],
        cwd=context.cwd,
        env=CHECKPOINT_ENV,
    )
    commit = resolve_commit(context.cwd, "HEAD")
    context.current_checkpoint = commit
    context.checkpoints.append(
        {
            "label": label,
            "commit": commit,
        }
    )
    return commit


def rollback_to_checkpoint(context: GitRunContext, commit: str, reason: str, cycle: int) -> None:
    run_git(["reset", "--hard", commit], cwd=context.cwd)
    run_git(["clean", "-fd"], cwd=context.cwd)
    context.current_checkpoint = commit
    context.rollbacks.append(
        {
            "cycle": cycle,
            "commit": commit,
            "reason": reason,
        }
    )


def describe_context(context: GitRunContext) -> dict[str, Any]:
    return {
        "mode": context.mode,
        "repo_root": str(context.repo_root),
        "base_ref": context.base_ref,
        "base_commit": context.base_commit,
        "cwd": str(context.cwd),
        "branch": context.branch,
        "worktree_path": str(context.worktree_path) if context.worktree_path else None,
        "current_checkpoint": context.current_checkpoint,
        "checkpoints": list(context.checkpoints),
        "rollbacks": list(context.rollbacks),
    }
