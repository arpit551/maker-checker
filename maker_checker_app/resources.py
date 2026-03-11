from __future__ import annotations

from pathlib import Path


PACKAGE_ROOT = Path(__file__).resolve().parent
DEFAULTS_DIR = PACKAGE_ROOT / "defaults"
DEFAULT_BRIEFS_DIR = DEFAULTS_DIR / "briefs"
DEFAULT_STAGE_TEMPLATES_DIR = DEFAULTS_DIR / "templates" / "stages"


def default_brief_path(name: str) -> Path:
    return (DEFAULT_BRIEFS_DIR / name).resolve()


def default_stage_template_path(stage_name: str) -> Path:
    return (DEFAULT_STAGE_TEMPLATES_DIR / f"{stage_name}.md").resolve()

