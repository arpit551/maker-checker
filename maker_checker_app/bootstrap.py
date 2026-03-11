from __future__ import annotations

import argparse
import sys
import textwrap
from pathlib import Path

from .models import REQUIRED_STAGES, WorkflowError
from .resources import (
    default_brief_path,
    default_stage_template_path,
    resolve_workspace_dir,
)

STAGE_AGENT_MAP = {
    "plan": "codex",
    "critique": "claude",
    "revise": "codex",
    "execute": "claude",
    "verify": "codex",
    "evaluate": "codex",
}


def build_default_config_text() -> str:
    stage_blocks = []
    for stage_name in REQUIRED_STAGES:
        stage_blocks.append(
            textwrap.dedent(
                f"""\
                [stages.{stage_name}]
                agent = "{STAGE_AGENT_MAP[stage_name]}"
                template_file = "templates/stages/{stage_name}.md"
                """
            ).strip()
        )

    return textwrap.dedent(
        """\
        [workflow]
        max_cycles = 3
        artifacts_dir = "runs"
        history_dir = "memory"
        history_limit = 2

        [git]
        mode = "worktree"
        base_ref = "HEAD"
        worktrees_dir = "worktrees"

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

        """
    ) + "\n".join(stage_blocks) + "\n"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Bootstrap a local maker-checker workspace inside .maker-checker."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Project directory where .maker-checker should be created.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite config and brief files if they already exist.",
    )
    return parser.parse_args()


def init_workspace(target_dir: Path, force: bool = False) -> list[Path]:
    project_dir = target_dir.expanduser().resolve()
    project_dir.mkdir(parents=True, exist_ok=True)
    workspace_dir = resolve_workspace_dir(project_dir)
    workspace_dir.mkdir(parents=True, exist_ok=True)

    config_path = workspace_dir / "config.toml"
    task_path = workspace_dir / "briefs" / "task.md"
    evaluation_path = workspace_dir / "briefs" / "evaluation.md"
    template_paths = [workspace_dir / "templates" / "stages" / f"{stage_name}.md" for stage_name in REQUIRED_STAGES]
    managed_paths = [config_path, task_path, evaluation_path, *template_paths]

    existing = [path for path in managed_paths if path.exists()]
    if existing and not force:
        joined = ", ".join(str(path) for path in existing)
        raise WorkflowError(
            f"Refusing to overwrite existing files: {joined}. Re-run with --force to replace them."
        )

    (workspace_dir / "briefs").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "templates" / "stages").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "runs").mkdir(parents=True, exist_ok=True)
    (workspace_dir / "memory").mkdir(parents=True, exist_ok=True)

    config_path.write_text(build_default_config_text(), encoding="utf-8")
    task_path.write_text(default_brief_path("task.md").read_text(encoding="utf-8"), encoding="utf-8")
    evaluation_path.write_text(
        default_brief_path("evaluation.md").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    for stage_name in REQUIRED_STAGES:
        (workspace_dir / "templates" / "stages" / f"{stage_name}.md").write_text(
            default_stage_template_path(stage_name).read_text(encoding="utf-8"),
            encoding="utf-8",
        )

    return [config_path, task_path, evaluation_path, *template_paths]


def main() -> int:
    args = parse_args()

    try:
        created = init_workspace(Path(args.directory), force=args.force)
        print("Created maker-checker workspace:")
        print(f"- {resolve_workspace_dir(Path(args.directory))}")
        print("Managed files:")
        for path in created:
            print(f"- {path}")
        return 0
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
