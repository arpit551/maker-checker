from __future__ import annotations

from pathlib import Path

from .models import DEFAULT_WORKSPACE_DIRNAME, REQUIRED_STAGES

PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULTS_DIR = PACKAGE_ROOT / "defaults"
DEFAULT_BRIEFS_DIR = DEFAULTS_DIR / "briefs"
DEFAULT_STAGE_TEMPLATES_DIR = DEFAULTS_DIR / "templates" / "stages"


def default_brief_path(name: str) -> Path:
    return (DEFAULT_BRIEFS_DIR / name).resolve()


def default_stage_template_path(stage_name: str) -> Path:
    return (DEFAULT_STAGE_TEMPLATES_DIR / f"{stage_name}.md").resolve()


def default_stage_template_paths() -> dict[str, Path]:
    return {
        stage_name: default_stage_template_path(stage_name)
        for stage_name in REQUIRED_STAGES
    }


def resolve_workspace_dir(project_dir: Path) -> Path:
    resolved = project_dir.expanduser().resolve()
    if resolved.name == DEFAULT_WORKSPACE_DIRNAME:
        return resolved
    return (resolved / DEFAULT_WORKSPACE_DIRNAME).resolve()
