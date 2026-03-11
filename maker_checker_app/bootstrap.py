from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from .resources import default_brief_path
from .models import WorkflowError


DEFAULT_CONFIG_TEXT = textwrap.dedent(
    """\
    [workflow]
    max_cycles = 3
    artifacts_dir = "runs"
    history_dir = "memory"
    history_limit = 3

    [inputs]
    task_prompt_file = "briefs/task.md"
    evaluation_prompt_file = "briefs/evaluation.md"

    [agents.codex]
    command = [
      "codex",
      "exec",
      "--skip-git-repo-check",
      "--dangerously-bypass-approvals-and-sandbox",
      "--ephemeral",
      "-c",
      "model_reasoning_effort=\\"low\\"",
      "-o",
      "{output_file}",
      "-"
    ]
    input_mode = "stdin"
    timeout_sec = 900

    [agents.claude]
    command = [
      "claude",
      "-p",
      "--dangerously-skip-permissions",
      "--no-session-persistence",
      "--session-id",
      "{session_id}"
    ]
    input_mode = "stdin"
    timeout_sec = 900

    [stages.plan]
    agent = "codex"

    [stages.critique]
    agent = "claude"

    [stages.revise]
    agent = "codex"

    [stages.execute]
    agent = "claude"

    [stages.verify]
    agent = "codex"

    [stages.evaluate]
    agent = "codex"
    """
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a local maker-checker workspace."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Directory where the config and briefs should be created.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite config and brief files if they already exist.",
    )
    return parser.parse_args()


def init_workspace(target_dir: Path, force: bool = False) -> list[Path]:
    target_dir = target_dir.expanduser().resolve()
    target_dir.mkdir(parents=True, exist_ok=True)

    config_path = target_dir / "config.toml"
    task_path = target_dir / "briefs" / "task.md"
    evaluation_path = target_dir / "briefs" / "evaluation.md"
    managed_paths = [config_path, task_path, evaluation_path]

    existing = [path for path in managed_paths if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise WorkflowError(
            f"Refusing to overwrite existing files: {joined}. Re-run with --force to replace them."
        )

    (target_dir / "briefs").mkdir(parents=True, exist_ok=True)
    (target_dir / "runs").mkdir(parents=True, exist_ok=True)
    (target_dir / "memory").mkdir(parents=True, exist_ok=True)

    config_path.write_text(DEFAULT_CONFIG_TEXT, encoding="utf-8")
    task_path.write_text(default_brief_path("task.md").read_text(encoding="utf-8"), encoding="utf-8")
    evaluation_path.write_text(
        default_brief_path("evaluation.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )

    return [config_path, task_path, evaluation_path]


def main() -> int:
    args = parse_args()

    try:
        created = init_workspace(Path(args.directory), force=args.force)
        print("Created maker-checker workspace:")
        for path in created:
            print(f"- {path}")
        return 0
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
