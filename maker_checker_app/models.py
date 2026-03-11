from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


REQUIRED_STAGES = ("plan", "critique", "revise", "execute", "verify", "evaluate")
STATE_SCHEMA_VERSION = "v1"
DEFAULT_TASK_BRIEF = "briefs/task.md"
DEFAULT_EVALUATION_BRIEF = "briefs/evaluation.md"
DEFAULT_HISTORY_DIR = "memory"
DEFAULT_HISTORY_LIMIT = 3

STATUS_PENDING = "pending"
STATUS_RUNNING = "running"
STATUS_COMPLETED = "completed"
STATUS_FAILED = "failed"
STATUS_TOKENS = {
    STATUS_PENDING: "todo",
    STATUS_RUNNING: "run",
    STATUS_COMPLETED: "done",
    STATUS_FAILED: "fail",
}


class WorkflowError(RuntimeError):
    """Raised when the configured workflow cannot continue."""


class SafeDict(dict[str, Any]):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class AgentConfig:
    name: str
    command: list[str]
    input_mode: str = "stdin"
    timeout_sec: int = 900


@dataclass
class StageConfig:
    name: str
    agent: str
    template_file: Path
    timeout_sec: int | None = None


@dataclass
class WorkflowConfig:
    max_cycles: int
    artifacts_dir: Path
    task_prompt_file: Path
    evaluation_prompt_file: Path
    agents: dict[str, AgentConfig]
    stages: dict[str, StageConfig]
    history_dir: Path | None = None
    history_limit: int = DEFAULT_HISTORY_LIMIT
