from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .models import SafeDict, WorkflowError


def read_text_file(path: Path, label: str) -> str:
    if not path.exists():
        raise WorkflowError(f"{label} not found: {path}")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise WorkflowError(f"{label} is empty: {path}")
    return content.strip()


def render_prompt(template_file: Path, context: dict[str, Any]) -> str:
    if not template_file.exists():
        raise WorkflowError(f"Template file not found: {template_file}")
    template = template_file.read_text(encoding="utf-8")
    return template.format_map(SafeDict(context)).strip() + "\n"


def dedupe_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for item in items:
        normalized = item.strip()
        if not normalized:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        out.append(normalized)
    return out


def extract_first_json(value: str) -> Any | None:
    decoder = json.JSONDecoder()
    for idx, char in enumerate(value):
        if char not in "[{":
            continue
        try:
            parsed, _ = decoder.raw_decode(value[idx:])
            return parsed
        except json.JSONDecodeError:
            continue
    return None


def parse_assessment(value: str) -> tuple[list[str], bool]:
    parsed = extract_first_json(value)
    issues: list[str] = []
    passed: bool | None = None

    if isinstance(parsed, dict):
        maybe_issues = parsed.get("issues")
        if isinstance(maybe_issues, list):
            issues = [str(x).strip() for x in maybe_issues if str(x).strip()]
        elif isinstance(maybe_issues, str) and maybe_issues.strip():
            issues = [maybe_issues.strip()]

        maybe_pass = parsed.get("pass")
        if isinstance(maybe_pass, bool):
            passed = maybe_pass

        if passed is None:
            maybe_status = parsed.get("status")
            if isinstance(maybe_status, str):
                lowered = maybe_status.lower().strip()
                if lowered in {"pass", "passed", "ok", "success"}:
                    passed = True
                elif lowered in {"fail", "failed", "error"}:
                    passed = False
    elif isinstance(parsed, list):
        issues = [str(x).strip() for x in parsed if str(x).strip()]

    if not issues and re.search(r"\bno\s+issues\b", value, flags=re.IGNORECASE):
        issues = []

    if passed is None:
        passed = len(issues) == 0

    return dedupe_preserve_order(issues), passed


def shorten_text(value: str, limit: int = 180) -> str:
    without_markers = re.sub(r"(?m)^\s*[-#*]+\s*", "", value)
    normalized = " ".join(without_markers.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def summarize_items(items: list[str], limit: int = 2) -> str:
    if not items:
        return "none"
    preview = items[:limit]
    text = "; ".join(preview)
    if len(items) > limit:
        text += f"; +{len(items) - limit} more"
    return text


def render_issue_bar(count: int) -> str:
    if count <= 0:
        return "(none)"
    return "#" * min(count, 20)


def build_cycle_context(
    base_context: dict[str, Any],
    stage_outputs: dict[str, str],
    cycle_index: int,
    max_cycles: int,
) -> dict[str, Any]:
    context = dict(base_context)
    context["cycle_index"] = cycle_index
    context["max_cycles"] = max_cycles

    for key, value in stage_outputs.items():
        context[f"{key}_output"] = value

    context.setdefault("plan_output", "")
    context.setdefault("critique_output", "")
    context.setdefault("revise_output", "")
    context.setdefault("execute_output", "")
    context.setdefault("verify_output", "")
    context.setdefault("evaluate_output", "")
    context.setdefault("recent_run_memory", "- No previous runs recorded.")

    return context
