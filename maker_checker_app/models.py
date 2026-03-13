from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


REQUIRED_STAGES = ("discover", "plan", "critique", "revise", "execute", "verify", "evaluate")
STATE_SCHEMA_VERSION = "v1"
DEFAULT_WORKSPACE_DIRNAME = ".maker-checker"
DEFAULT_CONFIG_FILE = f"{DEFAULT_WORKSPACE_DIRNAME}/config.toml"
DEFAULT_TASK_BRIEF = "briefs/task.md"
DEFAULT_EVALUATION_BRIEF = "briefs/evaluation.md"
DEFAULT_HISTORY_DIR = "memory"
DEFAULT_HISTORY_LIMIT = 2
DEFAULT_GIT_MODE = "worktree"
DEFAULT_GIT_BASE_REF = "HEAD"
DEFAULT_WORKTREES_DIRNAME = "worktrees"
DEFAULT_GIT_APPLY_ON_SUCCESS = False
GIT_MODES = ("worktree", "inplace")

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
class GitConfig:
    mode: str = DEFAULT_GIT_MODE
    base_ref: str = DEFAULT_GIT_BASE_REF
    worktrees_dir: Path | None = None
    apply_on_success: bool = DEFAULT_GIT_APPLY_ON_SUCCESS


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
    workspace_dir: Path | None = None
    project_dir: Path | None = None
    git: GitConfig = field(default_factory=GitConfig)
