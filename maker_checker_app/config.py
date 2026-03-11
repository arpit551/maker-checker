from __future__ import annotations

import shlex
from pathlib import Path
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from .models import (
    DEFAULT_EVALUATION_BRIEF,
    DEFAULT_HISTORY_DIR,
    DEFAULT_HISTORY_LIMIT,
    DEFAULT_TASK_BRIEF,
    REQUIRED_STAGES,
    AgentConfig,
    StageConfig,
    WorkflowConfig,
    WorkflowError,
)
from .resources import default_stage_template_path


def _resolve_path(raw: str, base_dir: Path) -> Path:
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = base_dir / path
    return path.resolve()


def _ensure_list_command(raw: Any, field_name: str) -> list[str]:
    if isinstance(raw, str):
        parts = shlex.split(raw)
        if not parts:
            raise WorkflowError(f"{field_name} must not be empty.")
        return parts
    if isinstance(raw, list) and raw and all(isinstance(x, str) and x for x in raw):
        return raw
    raise WorkflowError(f"{field_name} must be a command string or non-empty list of strings.")


def get_history_dir(config: WorkflowConfig) -> Path:
    if config.history_dir is not None:
        return config.history_dir
    return (config.artifacts_dir.parent / DEFAULT_HISTORY_DIR).resolve()


def load_config(config_path: Path) -> WorkflowConfig:
    if not config_path.exists():
        raise WorkflowError(f"Config file not found: {config_path}")

    base_dir = config_path.parent.resolve()
    with config_path.open("rb") as f:
        raw = tomllib.load(f)

    workflow_raw = raw.get("workflow", {})
    inputs_raw = raw.get("inputs", {})
    agents_raw = raw.get("agents", {})
    stages_raw = raw.get("stages", {})

    try:
        max_cycles = int(workflow_raw.get("max_cycles", 3))
    except (TypeError, ValueError) as exc:
        raise WorkflowError("workflow.max_cycles must be an integer.") from exc
    if max_cycles < 1:
        raise WorkflowError("workflow.max_cycles must be >= 1.")

    try:
        history_limit = int(workflow_raw.get("history_limit", DEFAULT_HISTORY_LIMIT))
    except (TypeError, ValueError) as exc:
        raise WorkflowError("workflow.history_limit must be an integer.") from exc
    if history_limit < 1:
        raise WorkflowError("workflow.history_limit must be >= 1.")

    artifacts_dir = _resolve_path(workflow_raw.get("artifacts_dir", "runs"), base_dir)
    history_dir = _resolve_path(workflow_raw.get("history_dir", DEFAULT_HISTORY_DIR), base_dir)
    task_prompt_file = _resolve_path(
        inputs_raw.get("task_prompt_file", DEFAULT_TASK_BRIEF),
        base_dir,
    )
    evaluation_prompt_file = _resolve_path(
        inputs_raw.get("evaluation_prompt_file", DEFAULT_EVALUATION_BRIEF),
        base_dir,
    )

    if not agents_raw:
        raise WorkflowError("No agents configured. Add [agents.<name>] entries to config.toml.")

    agents: dict[str, AgentConfig] = {}
    for agent_name, agent_raw in agents_raw.items():
        command = _ensure_list_command(agent_raw.get("command"), f"agents.{agent_name}.command")
        input_mode = agent_raw.get("input_mode", "stdin")
        if input_mode not in {"stdin", "file"}:
            raise WorkflowError(
                f"agents.{agent_name}.input_mode must be 'stdin' or 'file', got {input_mode!r}."
            )
        timeout_sec = int(agent_raw.get("timeout_sec", 900))
        agents[agent_name] = AgentConfig(
            name=agent_name,
            command=command,
            input_mode=input_mode,
            timeout_sec=timeout_sec,
        )

    stages: dict[str, StageConfig] = {}
    for stage_name in REQUIRED_STAGES:
        stage_raw = stages_raw.get(stage_name)
        if not stage_raw:
            raise WorkflowError(f"Missing stage configuration: [stages.{stage_name}]")
        agent = stage_raw.get("agent")
        if not isinstance(agent, str) or not agent:
            raise WorkflowError(f"stages.{stage_name}.agent is required.")
        if agent not in agents:
            raise WorkflowError(
                f"stages.{stage_name}.agent references unknown agent {agent!r}."
            )
        template_file_raw = stage_raw.get("template_file")
        if template_file_raw is None:
            template_file = default_stage_template_path(stage_name)
        elif isinstance(template_file_raw, str) and template_file_raw:
            template_file = _resolve_path(template_file_raw, base_dir)
        else:
            raise WorkflowError(f"stages.{stage_name}.template_file must be a non-empty string if provided.")
        timeout_sec = stage_raw.get("timeout_sec")
        stages[stage_name] = StageConfig(
            name=stage_name,
            agent=agent,
            template_file=template_file,
            timeout_sec=int(timeout_sec) if timeout_sec is not None else None,
        )

    return WorkflowConfig(
        max_cycles=max_cycles,
        artifacts_dir=artifacts_dir,
        task_prompt_file=task_prompt_file,
        evaluation_prompt_file=evaluation_prompt_file,
        agents=agents,
        stages=stages,
        history_dir=history_dir,
        history_limit=history_limit,
    )
