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
    project_dir: Path
    base_ref: str
    base_commit: str
    cwd: Path
    branch: str | None = None
    worktree_path: Path | None = None
    current_checkpoint: str | None = None
    checkpoints: list[dict[str, Any]] = field(default_factory=list)
    rollbacks: list[dict[str, Any]] = field(default_factory=list)
    apply_result: dict[str, Any] | None = None


def _project_relative_path(project_dir: Path, repo_root: Path) -> Path:
    try:
        relative = project_dir.resolve().relative_to(repo_root.resolve())
    except ValueError as exc:
        raise WorkflowError(f"Project directory {project_dir} is not inside git repo {repo_root}.") from exc
    return relative


def _sync_linked_paths(source_project_dir: Path, target_project_dir: Path, linked_paths: tuple[str, ...]) -> list[str]:
    synced: list[str] = []
    for raw_path in linked_paths:
        relative_path = Path(raw_path)
        source_path = source_project_dir / relative_path
        if not source_path.exists() and not source_path.is_symlink():
            continue
        target_path = target_project_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists() or target_path.is_symlink():
            try:
                if target_path.is_symlink() and target_path.resolve() == source_path.resolve():
                    synced.append(raw_path)
            except OSError:
                pass
            continue
        target_path.symlink_to(source_path, target_is_directory=source_path.is_dir())
        synced.append(raw_path)
    return synced


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


def run_git_with_input(
    args: list[str],
    cwd: Path,
    input_text: str,
    env: dict[str, str] | None = None,
) -> str:
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.run(
        ["git", *args],
        cwd=cwd,
        env=merged_env,
        input=input_text,
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
    project_dir = project_dir.resolve()
    repo_root = resolve_repo_root(project_dir)
    base_commit = resolve_commit(repo_root, git_config.base_ref)
    project_relative = _project_relative_path(project_dir, repo_root)

    if git_config.mode == "inplace":
        return GitRunContext(
            mode="inplace",
            repo_root=repo_root,
            project_dir=project_dir,
            base_ref=git_config.base_ref,
            base_commit=base_commit,
            cwd=project_dir,
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
    worktree_project_dir = (worktree_path / project_relative).resolve()
    _sync_linked_paths(project_dir, worktree_project_dir, git_config.linked_paths)
    return GitRunContext(
        mode="worktree",
        repo_root=repo_root,
        project_dir=project_dir,
        base_ref=git_config.base_ref,
        base_commit=base_commit,
        cwd=worktree_project_dir,
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


def apply_run_changes(context: GitRunContext, run_id: str) -> dict[str, Any]:
    if context.mode != "worktree":
        result = {"status": "not_needed", "reason": "run executed in-place"}
        context.apply_result = result
        return result

    if context.current_checkpoint is None or context.current_checkpoint == context.base_commit:
        result = {"status": "no_changes", "reason": "run produced no committed diff"}
        context.apply_result = result
        return result

    current_head = resolve_commit(context.repo_root, "HEAD")
    if current_head != context.base_commit:
        result = {
            "status": "skipped",
            "reason": "base checkout moved since the run started",
            "target_head": current_head,
        }
        context.apply_result = result
        return result

    porcelain = run_git(["status", "--porcelain", "--untracked-files=no"], cwd=context.repo_root)
    if porcelain.strip():
        result = {
            "status": "skipped",
            "reason": "base checkout has tracked changes",
        }
        context.apply_result = result
        return result

    patch = subprocess.run(
        ["git", "diff", "--binary", context.base_commit, context.current_checkpoint],
        cwd=context.cwd,
        capture_output=True,
        text=True,
        check=False,
    )
    if patch.returncode != 0:
        raise WorkflowError(
            f"git diff failed while preparing apply-back for run {run_id}: "
            f"{patch.stderr.strip() or patch.stdout.strip() or 'unknown error'}"
        )
    if not patch.stdout.strip():
        result = {"status": "no_changes", "reason": "run produced no diff against the base commit"}
        context.apply_result = result
        return result

    run_git_with_input(["apply", "--check", "--index", "--3way", "-"], cwd=context.repo_root, input_text=patch.stdout)
    run_git_with_input(["apply", "--index", "--3way", "-"], cwd=context.repo_root, input_text=patch.stdout)
    try:
        target_branch = run_git(["rev-parse", "--abbrev-ref", "HEAD"], cwd=context.repo_root)
    except WorkflowError:
        target_branch = None
    result = {
        "status": "applied",
        "reason": "applied successful run changes back to the base checkout",
        "target_head": current_head,
        "target_branch": target_branch,
        "applied_commit": context.current_checkpoint,
    }
    context.apply_result = result
    return result


def describe_context(context: GitRunContext) -> dict[str, Any]:
    return {
        "mode": context.mode,
        "repo_root": str(context.repo_root),
        "project_dir": str(context.project_dir),
        "base_ref": context.base_ref,
        "base_commit": context.base_commit,
        "cwd": str(context.cwd),
        "branch": context.branch,
        "worktree_path": str(context.worktree_path) if context.worktree_path else None,
        "current_checkpoint": context.current_checkpoint,
        "checkpoints": list(context.checkpoints),
        "rollbacks": list(context.rollbacks),
        "apply_result": context.apply_result,
    }
