from __future__ import annotations

import json
import shlex
import subprocess
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

from .config import get_history_dir
from .models import (
    REQUIRED_STAGES,
    STATUS_COMPLETED,
    STATUS_FAILED,
    STATUS_PENDING,
    STATUS_RUNNING,
    STATUS_TOKENS,
    AgentConfig,
    StageConfig,
    WorkflowConfig,
    WorkflowError,
)
from .text import (
    build_cycle_context,
    dedupe_preserve_order,
    parse_assessment,
    read_text_file,
    render_issue_bar,
    render_prompt,
    shorten_text,
    summarize_items,
)


def load_history_entries(history_dir: Path) -> list[dict[str, Any]]:
    jsonl_path = history_dir / "run_history.jsonl"
    if not jsonl_path.exists():
        return []

    entries: list[dict[str, Any]] = []
    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            entries.append(parsed)
    return entries


def render_history_context(entries: list[dict[str, Any]], limit: int) -> str:
    if not entries:
        return "- No previous runs recorded."

    lines: list[str] = []
    for entry in entries[-limit:]:
        lines.append(f"### {entry['run_id']}")
        lines.append(f"- Outcome: {entry['outcome']}")
        lines.append(f"- Issue trend: {entry.get('issue_trend', 'n/a')}")
        for item in entry.get("improvements", [])[:2]:
            lines.append(f"- Improved: {item}")
        for item in entry.get("failures", [])[:2]:
            lines.append(f"- Failed: {item}")
        for item in entry.get("next_run_notes", [])[:2]:
            lines.append(f"- Reuse: {item}")
        lines.append("")
    return "\n".join(lines).strip()


def append_event(run_dir: Path, message: str) -> None:
    timestamp = datetime.now().isoformat(timespec="seconds")
    with (run_dir / "events.log").open("a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {message}\n")


def read_event_tail(run_dir: Path, limit: int = 20) -> list[str]:
    log_file = run_dir / "events.log"
    if not log_file.exists():
        return []
    return log_file.read_text(encoding="utf-8").splitlines()[-limit:]


def read_stage_output_excerpt(stage_dir: Path, limit: int = 320) -> str:
    for filename in ("assistant_output.txt", "stdout.txt", "stderr.txt"):
        path = stage_dir / filename
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return shorten_text(text, limit=limit)
    return ""


def build_stage_snapshot(
    config: WorkflowConfig,
    run_dir: Path,
    progress: dict[int, dict[str, str]],
    cycle_number: int,
    stage_name: str,
    step_index: int,
) -> dict[str, Any]:
    stage_dir = run_dir / f"cycle-{cycle_number:02d}" / f"{step_index:02d}-{stage_name}"
    command = (stage_dir / "command.txt").read_text(encoding="utf-8").strip() if (stage_dir / "command.txt").exists() else ""
    elapsed_text = (stage_dir / "elapsed_sec.txt").read_text(encoding="utf-8").strip() if (stage_dir / "elapsed_sec.txt").exists() else ""
    elapsed = float(elapsed_text) if elapsed_text else None
    return {
        "stage": stage_name,
        "status": progress[cycle_number][stage_name],
        "agent": config.stages[stage_name].agent,
        "elapsed_sec": elapsed,
        "command": command,
        "output_excerpt": read_stage_output_excerpt(stage_dir),
    }


def build_cycle_notes(cycles: list[dict[str, Any]]) -> tuple[list[str], list[str]]:
    improvements: list[str] = []
    failures: list[str] = []

    if not cycles:
        return improvements, failures

    first_count = len(cycles[0]["issues"])
    final_count = len(cycles[-1]["issues"])
    if final_count < first_count:
        improvements.append(f"Issue count dropped from {first_count} to {final_count}.")
    elif final_count > first_count:
        failures.append(f"Issue count grew from {first_count} to {final_count}.")

    previous_issues: list[str] | None = None
    for cycle in cycles:
        current_issues = cycle["issues"]
        cycle_num = cycle["cycle"]
        if previous_issues is not None:
            resolved = [item for item in previous_issues if item not in current_issues]
            added = [item for item in current_issues if item not in previous_issues]
            if resolved:
                improvements.append(
                    f"Cycle {cycle_num} resolved {len(resolved)} issue(s): {summarize_items(resolved)}."
                )
            if added:
                failures.append(
                    f"Cycle {cycle_num} introduced {len(added)} new issue(s): {summarize_items(added)}."
                )
            if not resolved and not added:
                failures.append(f"Cycle {cycle_num} repeated the previous issue set.")
        previous_issues = current_issues

    return dedupe_preserve_order(improvements), dedupe_preserve_order(failures)


def build_history_entry(
    run_dir: Path,
    summary: dict[str, Any],
    task_prompt: str,
    evaluation_prompt: str,
) -> dict[str, Any]:
    cycles = summary.get("cycles", [])
    improvements, failures = build_cycle_notes(cycles)

    if summary.get("completed"):
        outcome = "completed"
        improvements.append("Run finished without unresolved issues.")
    elif summary.get("failure"):
        outcome = "failed"
        failures.append(summary["failure"]["error"])
    else:
        outcome = "incomplete"

    final_issues: list[str] = cycles[-1]["issues"] if cycles else []
    if final_issues:
        failures.extend(final_issues[:3])

    next_run_notes: list[str] = []
    if not cycles and summary.get("failure"):
        next_run_notes.append("Fix the workflow failure before retrying the same task.")
    if cycles:
        first_count = len(cycles[0]["issues"])
        final_count = len(cycles[-1]["issues"])
        if final_count >= first_count and final_count > 0:
            next_run_notes.append(
                "Use a tighter task brief; unresolved issues did not trend down cleanly."
            )
    next_run_notes.extend(final_issues[:3])
    if not next_run_notes and summary.get("completed"):
        next_run_notes.append("Reuse this prompt structure; the run converged successfully.")

    issue_counts = [len(cycle["issues"]) for cycle in cycles]
    issue_trend = " -> ".join(str(count) for count in issue_counts) if issue_counts else "n/a"

    return {
        "run_id": run_dir.name,
        "outcome": outcome,
        "task_excerpt": shorten_text(task_prompt),
        "evaluation_excerpt": shorten_text(evaluation_prompt),
        "issue_trend": issue_trend,
        "improvements": dedupe_preserve_order(improvements)[:4],
        "failures": dedupe_preserve_order(failures)[:4],
        "next_run_notes": dedupe_preserve_order(next_run_notes)[:4],
        "summary_path": str(run_dir / "run_summary.md"),
        "ended_at": summary.get("ended_at", ""),
    }


def write_history_files(history_dir: Path, entries: list[dict[str, Any]]) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    jsonl_path = history_dir / "run_history.jsonl"
    md_path = history_dir / "run_history.md"

    jsonl_path.write_text(
        "".join(json.dumps(entry, ensure_ascii=True) + "\n" for entry in entries),
        encoding="utf-8",
    )

    lines = [
        "# Run History",
        "",
        "This file captures what each run tried, what improved, and what should carry into the next run.",
        "",
    ]
    if not entries:
        lines.append("- No runs recorded yet.")
    for entry in entries:
        lines.append(f"## {entry['run_id']}")
        lines.append(f"- Outcome: {entry['outcome']}")
        lines.append(f"- Task brief: {entry['task_excerpt']}")
        lines.append(f"- Evaluation brief: {entry['evaluation_excerpt']}")
        lines.append(f"- Issue trend: {entry['issue_trend']}")
        if entry.get("improvements"):
            lines.append("- Improvements:")
            for item in entry["improvements"]:
                lines.append(f"  - {item}")
        if entry.get("failures"):
            lines.append("- Failures:")
            for item in entry["failures"]:
                lines.append(f"  - {item}")
        if entry.get("next_run_notes"):
            lines.append("- Reuse Next Run:")
            for item in entry["next_run_notes"]:
                lines.append(f"  - {item}")
        lines.append(f"- Summary: {entry['summary_path']}")
        lines.append("")

    md_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")


def append_history_entry(history_dir: Path, entry: dict[str, Any]) -> None:
    entries = load_history_entries(history_dir)
    entries.append(entry)
    write_history_files(history_dir, entries)


def init_progress(max_cycles: int) -> dict[int, dict[str, str]]:
    return {
        cycle: {stage: STATUS_PENDING for stage in REQUIRED_STAGES}
        for cycle in range(1, max_cycles + 1)
    }


def build_status_payload(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    progress: dict[int, dict[str, str]],
    state: str,
    active_cycle: int | None,
    active_stage: str | None,
) -> dict[str, Any]:
    cycles = []
    cycle_lookup = {cycle["cycle"]: cycle for cycle in summary.get("cycles", [])}
    started_cycle_numbers: list[int] = []
    for cycle_number in range(1, config.max_cycles + 1):
        stage_states = progress[cycle_number]
        has_started = any(value != STATUS_PENDING for value in stage_states.values()) or cycle_number in cycle_lookup
        if not has_started:
            continue
        started_cycle_numbers.append(cycle_number)
        record = cycle_lookup.get(cycle_number, {})
        stage_snapshots = [
            build_stage_snapshot(config, run_dir, progress, cycle_number, stage_name, step_index)
            for step_index, stage_name in enumerate(REQUIRED_STAGES, start=1)
        ]
        cycles.append(
            {
                "cycle": cycle_number,
                "stages": stage_states,
                "stage_details": stage_snapshots,
                "issues": record.get("issues", []),
                "issues_count": len(record.get("issues", [])),
                "elapsed_sec": record.get("elapsed_sec"),
                "verify_pass": record.get("verify_pass"),
                "evaluate_pass": record.get("evaluate_pass"),
                "stage_timings_sec": record.get("stage_timings_sec", {}),
            }
        )

    active_run_cycle = active_cycle
    if active_run_cycle is None and started_cycle_numbers:
        active_run_cycle = started_cycle_numbers[-1]

    next_stage = None
    if active_stage is not None and active_cycle is not None:
        next_stage = active_stage
    else:
        for cycle_number in range(1, config.max_cycles + 1):
            for stage_name in REQUIRED_STAGES:
                if progress[cycle_number][stage_name] == STATUS_PENDING:
                    next_stage = f"cycle {cycle_number} / {stage_name}"
                    break
            if next_stage:
                break

    completed_stage_count = sum(
        1 for cycle in progress.values() for status_value in cycle.values() if status_value == STATUS_COMPLETED
    )
    total_stage_count = config.max_cycles * len(REQUIRED_STAGES)
    latest_cycle = cycles[-1] if cycles else None
    evaluation_state = {
        "verify_pass": latest_cycle.get("verify_pass") if latest_cycle else None,
        "evaluate_pass": latest_cycle.get("evaluate_pass") if latest_cycle else None,
        "issues_count": latest_cycle.get("issues_count") if latest_cycle else 0,
        "issues": latest_cycle.get("issues", []) if latest_cycle else [],
    }

    what_happened = read_event_tail(run_dir, limit=6)
    what_is_happening = (
        f"Running cycle {active_cycle}, stage {active_stage}."
        if active_cycle and active_stage
        else "No stage is currently running."
    )
    what_happens_next = (
        "Run completes if verify/evaluate leave no unresolved issues."
        if summary.get("completed")
        else (f"Next expected step: {next_stage}." if next_stage else "No further steps are queued.")
    )

    return {
        "run_id": run_dir.name,
        "state": state,
        "active_cycle": active_cycle,
        "active_stage": active_stage,
        "next_stage": next_stage,
        "started_at": summary.get("started_at"),
        "ended_at": summary.get("ended_at"),
        "updated_at": datetime.now().isoformat(timespec="seconds"),
        "max_cycles": config.max_cycles,
        "stage_position": {
            "completed": completed_stage_count,
            "total": total_stage_count,
        },
        "task_brief_path": str(config.task_prompt_file),
        "evaluation_brief_path": str(config.evaluation_prompt_file),
        "history_file": str(get_history_dir(config) / "run_history.md"),
        "summary_file": str(run_dir / "summary.json"),
        "run_summary_file": str(run_dir / "run_summary.md"),
        "status_file": str(run_dir / "status.md"),
        "failure": summary.get("failure"),
        "history_loaded": summary.get("history_loaded", False),
        "active_cycle_snapshot": next((cycle for cycle in cycles if cycle["cycle"] == active_run_cycle), None),
        "evaluation_state": evaluation_state,
        "what_happened": what_happened,
        "what_is_happening": what_is_happening,
        "what_happens_next": what_happens_next,
        "cycles": cycles,
        "recent_events": read_event_tail(run_dir),
    }


def render_status_markdown(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    progress: dict[int, dict[str, str]],
    state: str,
    active_cycle: int | None,
    active_stage: str | None,
) -> str:
    history_dir = get_history_dir(config)
    cycle_lookup = {cycle["cycle"]: cycle for cycle in summary.get("cycles", [])}
    started_cycles = [
        cycle
        for cycle in range(1, config.max_cycles + 1)
        if any(progress[cycle][stage] != STATUS_PENDING for stage in REQUIRED_STAGES)
        or cycle in cycle_lookup
    ]
    if not started_cycles:
        started_cycles = [1]

    lines = [
        "# Run Status",
        "",
        f"- Run: {run_dir.name}",
        f"- State: {state}",
        f"- Active: cycle {active_cycle} / {active_stage}"
        if active_cycle and active_stage
        else "- Active: idle",
        f"- Started: {summary.get('started_at', 'n/a')}",
        f"- Max cycles: {config.max_cycles}",
        f"- Task brief: {config.task_prompt_file}",
        f"- Evaluation brief: {config.evaluation_prompt_file}",
        f"- History log: {history_dir / 'run_history.md'}",
        "",
        "## Progress",
        "",
        "| Cycle | plan | critique | revise | execute | verify | evaluate | Issues | Duration |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]

    for cycle in started_cycles:
        record = cycle_lookup.get(cycle)
        row = [
            str(cycle),
            *(STATUS_TOKENS[progress[cycle][stage]] for stage in REQUIRED_STAGES),
            str(len(record["issues"])) if record else "-",
            f"{record['elapsed_sec']:.1f}s" if record else "-",
        ]
        lines.append("| " + " | ".join(row) + " |")

    lines.extend(
        [
            "",
            "Legend: `todo` pending, `run` in progress, `done` complete, `fail` stage failure.",
        ]
    )

    cycles = summary.get("cycles", [])
    if cycles:
        lines.extend(
            [
                "",
                "## Issue Trend",
                "",
                "| Cycle | Count | Trend |",
                "| --- | --- | --- |",
            ]
        )
        for cycle in cycles:
            count = len(cycle["issues"])
            lines.append(f"| {cycle['cycle']} | {count} | {render_issue_bar(count)} |")

    if summary.get("failure"):
        lines.extend(["", "## Failure", "", f"- {summary['failure']['error']}"])

    return "\n".join(lines).rstrip() + "\n"


def write_status_files(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    progress: dict[int, dict[str, str]],
    state: str,
    active_cycle: int | None = None,
    active_stage: str | None = None,
) -> None:
    payload = build_status_payload(
        config=config,
        run_dir=run_dir,
        summary=summary,
        progress=progress,
        state=state,
        active_cycle=active_cycle,
        active_stage=active_stage,
    )
    markdown = render_status_markdown(
        config=config,
        run_dir=run_dir,
        summary=summary,
        progress=progress,
        state=state,
        active_cycle=active_cycle,
        active_stage=active_stage,
    )
    (run_dir / "status.md").write_text(markdown, encoding="utf-8")
    (run_dir / "status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")
    config.artifacts_dir.mkdir(parents=True, exist_ok=True)
    (config.artifacts_dir / "latest_status.md").write_text(markdown, encoding="utf-8")
    (config.artifacts_dir / "latest_status.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def render_run_summary_markdown(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    task_prompt: str,
    evaluation_prompt: str,
    history_entry: dict[str, Any],
) -> str:
    cycles = summary.get("cycles", [])
    total_elapsed = sum(float(cycle.get("elapsed_sec", 0)) for cycle in cycles)
    lines = [
        "# Run Summary",
        "",
        f"- Run: {run_dir.name}",
        f"- Outcome: {history_entry['outcome']}",
        f"- Started: {summary.get('started_at', 'n/a')}",
        f"- Ended: {summary.get('ended_at', 'n/a')}",
        f"- Approx elapsed: {total_elapsed:.1f}s",
        f"- Task brief: {shorten_text(task_prompt)}",
        f"- Evaluation brief: {shorten_text(evaluation_prompt)}",
        f"- Status view: {run_dir / 'status.md'}",
        f"- History log: {get_history_dir(config) / 'run_history.md'}",
        "",
    ]

    if cycles:
        lines.extend(
            [
                "## Cycles",
                "",
                "| Cycle | Verify | Evaluate | Issues | Duration |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for cycle in cycles:
            lines.append(
                "| "
                + " | ".join(
                    [
                        str(cycle["cycle"]),
                        "pass" if cycle["verify_pass"] else "fail",
                        "pass" if cycle["evaluate_pass"] else "fail",
                        str(len(cycle["issues"])),
                        f"{cycle['elapsed_sec']:.1f}s",
                    ]
                )
                + " |"
            )
    else:
        lines.extend(["## Cycles", "", "- No cycle completed."])

    if history_entry["improvements"]:
        lines.extend(["", "## What Improved", ""])
        for item in history_entry["improvements"]:
            lines.append(f"- {item}")

    if history_entry["failures"]:
        lines.extend(["", "## What Failed", ""])
        for item in history_entry["failures"]:
            lines.append(f"- {item}")

    if history_entry["next_run_notes"]:
        lines.extend(["", "## Reuse Next Run", ""])
        for item in history_entry["next_run_notes"]:
            lines.append(f"- {item}")

    return "\n".join(lines).rstrip() + "\n"


def write_run_summary(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    task_prompt: str,
    evaluation_prompt: str,
    history_entry: dict[str, Any],
) -> None:
    markdown = render_run_summary_markdown(
        config=config,
        run_dir=run_dir,
        summary=summary,
        task_prompt=task_prompt,
        evaluation_prompt=evaluation_prompt,
        history_entry=history_entry,
    )
    (run_dir / "run_summary.md").write_text(markdown, encoding="utf-8")
    (config.artifacts_dir / "latest_summary.md").write_text(markdown, encoding="utf-8")


def finalize_run(
    config: WorkflowConfig,
    run_dir: Path,
    summary: dict[str, Any],
    task_prompt: str,
    evaluation_prompt: str,
    current_plan: str,
    progress: dict[int, dict[str, str]],
    state: str,
    active_cycle: int | None = None,
    active_stage: str | None = None,
) -> None:
    history_dir = get_history_dir(config)
    summary["status_file"] = str(run_dir / "status.md")
    summary["run_summary_file"] = str(run_dir / "run_summary.md")
    summary["history_file"] = str(history_dir / "run_history.md")

    (run_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    (run_dir / "final_plan.md").write_text(current_plan or "", encoding="utf-8")
    (run_dir / "task_brief.md").write_text(task_prompt, encoding="utf-8")
    (run_dir / "evaluation_brief.md").write_text(evaluation_prompt, encoding="utf-8")

    write_status_files(
        config=config,
        run_dir=run_dir,
        summary=summary,
        progress=progress,
        state=state,
        active_cycle=active_cycle,
        active_stage=active_stage,
    )

    history_entry = build_history_entry(run_dir, summary, task_prompt, evaluation_prompt)
    write_run_summary(
        config=config,
        run_dir=run_dir,
        summary=summary,
        task_prompt=task_prompt,
        evaluation_prompt=evaluation_prompt,
        history_entry=history_entry,
    )
    append_history_entry(history_dir, history_entry)


def run_stage(
    stage: StageConfig,
    agent: AgentConfig,
    prompt: str,
    stage_dir: Path,
) -> tuple[str, float]:
    stage_dir.mkdir(parents=True, exist_ok=True)
    prompt_suffix = stage.template_file.suffix or ".txt"
    prompt_file = stage_dir / f"prompt{prompt_suffix}"
    output_file = stage_dir / "assistant_output.txt"
    session_id = str(uuid.uuid4())
    prompt_file.write_text(prompt, encoding="utf-8")
    (stage_dir / "session_id.txt").write_text(session_id, encoding="utf-8")

    command = [
        part.replace("{prompt_file}", str(prompt_file))
        .replace("{output_file}", str(output_file))
        .replace("{stage_dir}", str(stage_dir))
        .replace("{session_id}", session_id)
        for part in agent.command
    ]

    timeout = stage.timeout_sec or agent.timeout_sec

    t0 = time.monotonic()
    try:
        if agent.input_mode == "stdin":
            proc = subprocess.run(
                command,
                input=prompt,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
        else:
            proc = subprocess.run(
                command,
                text=True,
                capture_output=True,
                timeout=timeout,
            )
    except FileNotFoundError as exc:
        raise WorkflowError(f"Command not found for agent {agent.name!r}: {command[0]!r}.") from exc
    except subprocess.TimeoutExpired as exc:
        raise WorkflowError(
            f"Stage {stage.name!r} timed out after {timeout}s while running {agent.name!r}."
        ) from exc
    finally:
        elapsed = round(time.monotonic() - t0, 3)

    (stage_dir / "stdout.txt").write_text(proc.stdout or "", encoding="utf-8")
    (stage_dir / "stderr.txt").write_text(proc.stderr or "", encoding="utf-8")
    (stage_dir / "exit_code.txt").write_text(str(proc.returncode), encoding="utf-8")
    (stage_dir / "command.txt").write_text(" ".join(shlex.quote(x) for x in command), encoding="utf-8")
    (stage_dir / "elapsed_sec.txt").write_text(str(elapsed), encoding="utf-8")

    if proc.returncode != 0:
        stderr_tail = (proc.stderr or "").strip().splitlines()[-1] if proc.stderr else ""
        raise WorkflowError(
            f"Stage {stage.name!r} failed with exit code {proc.returncode}. {stderr_tail}".strip()
        )

    if output_file.exists():
        cleaned = output_file.read_text(encoding="utf-8").strip()
        if cleaned:
            return cleaned, elapsed

    return (proc.stdout or "").strip(), elapsed


def run_workflow(config: WorkflowConfig, run_name: str | None = None) -> Path:
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    suffix = f"-{run_name}" if run_name else ""
    run_dir = config.artifacts_dir / f"{timestamp}{suffix}"
    run_dir.mkdir(parents=True, exist_ok=False)

    task_prompt = read_text_file(config.task_prompt_file, "Task brief file")
    evaluation_prompt = read_text_file(config.evaluation_prompt_file, "Evaluation brief file")
    history_entries = load_history_entries(get_history_dir(config))
    history_context = render_history_context(history_entries, config.history_limit)

    base_context: dict[str, Any] = {
        "task_prompt": task_prompt,
        "evaluation_prompt": evaluation_prompt,
        "previous_plan": "",
        "previous_execution_output": "",
        "previous_verification_output": "",
        "previous_evaluation_output": "",
        "unresolved_issues_bulleted": "- None",
        "unresolved_issues_json": "[]",
        "recent_run_memory": history_context,
    }

    summary: dict[str, Any] = {
        "started_at": datetime.now().isoformat(timespec="seconds"),
        "run_dir": str(run_dir),
        "max_cycles": config.max_cycles,
        "cycles": [],
        "completed": False,
        "failure": None,
        "history_loaded": bool(history_entries),
    }
    progress = init_progress(config.max_cycles)
    current_plan = ""
    append_event(run_dir, "run created")

    write_status_files(
        config=config,
        run_dir=run_dir,
        summary=summary,
        progress=progress,
        state="running",
    )

    for cycle in range(1, config.max_cycles + 1):
        print(f"[cycle {cycle}] starting")
        append_event(run_dir, f"cycle {cycle} started")
        cycle_dir = run_dir / f"cycle-{cycle:02d}"
        cycle_dir.mkdir(parents=True, exist_ok=True)
        stage_outputs: dict[str, str] = {}
        stage_timings: dict[str, float] = {}
        cycle_t0 = time.monotonic()

        try:
            for step_index, stage_name in enumerate(REQUIRED_STAGES, start=1):
                stage = config.stages[stage_name]
                agent = config.agents[stage.agent]
                stage_dir = cycle_dir / f"{step_index:02d}-{stage_name}"
                context = build_cycle_context(base_context, stage_outputs, cycle, config.max_cycles)
                prompt = render_prompt(stage.template_file, context)

                progress[cycle][stage_name] = STATUS_RUNNING
                write_status_files(
                    config=config,
                    run_dir=run_dir,
                    summary=summary,
                    progress=progress,
                    state="running",
                    active_cycle=cycle,
                    active_stage=stage_name,
                )

                print(f"[cycle {cycle}] {stage_name} -> {agent.name}")
                append_event(run_dir, f"cycle {cycle} stage {stage_name} started via {agent.name}")
                output, elapsed = run_stage(stage, agent, prompt, stage_dir)
                stage_outputs[stage_name] = output
                stage_timings[stage_name] = elapsed
                progress[cycle][stage_name] = STATUS_COMPLETED

                print(f"[cycle {cycle}] {stage_name} completed in {elapsed:.1f}s")
                append_event(run_dir, f"cycle {cycle} stage {stage_name} completed in {elapsed:.1f}s")
                write_status_files(
                    config=config,
                    run_dir=run_dir,
                    summary=summary,
                    progress=progress,
                    state="running",
                    active_cycle=cycle,
                    active_stage=stage_name,
                )

        except WorkflowError as exc:
            progress[cycle][stage_name] = STATUS_FAILED
            summary["failure"] = {"cycle": cycle, "error": str(exc)}
            summary["completed"] = False
            summary["ended_at"] = datetime.now().isoformat(timespec="seconds")
            append_event(run_dir, f"cycle {cycle} stage {stage_name} failed: {exc}")
            finalize_run(
                config=config,
                run_dir=run_dir,
                summary=summary,
                task_prompt=task_prompt,
                evaluation_prompt=evaluation_prompt,
                current_plan=current_plan,
                progress=progress,
                state="failed",
                active_cycle=cycle,
                active_stage=stage_name,
            )
            raise

        plan_output = stage_outputs.get("plan", "")
        revised_output = stage_outputs.get("revise", "").strip() or plan_output
        execution_output = stage_outputs.get("execute", "")
        verification_output = stage_outputs.get("verify", "")
        evaluation_output = stage_outputs.get("evaluate", "")

        verify_issues, verify_pass = parse_assessment(verification_output)
        eval_issues, eval_pass = parse_assessment(evaluation_output)
        unresolved = dedupe_preserve_order(verify_issues + eval_issues)

        current_plan = revised_output
        base_context["previous_plan"] = current_plan
        base_context["previous_execution_output"] = execution_output
        base_context["previous_verification_output"] = verification_output
        base_context["previous_evaluation_output"] = evaluation_output
        base_context["unresolved_issues_bulleted"] = (
            "\n".join(f"- {issue}" for issue in unresolved) if unresolved else "- None"
        )
        base_context["unresolved_issues_json"] = json.dumps(unresolved, ensure_ascii=True, indent=2)

        cycle_elapsed = round(time.monotonic() - cycle_t0, 3)
        cycle_record = {
            "cycle": cycle,
            "verify_pass": verify_pass,
            "evaluate_pass": eval_pass,
            "issues": unresolved,
            "elapsed_sec": cycle_elapsed,
            "stage_timings_sec": stage_timings,
        }
        summary["cycles"].append(cycle_record)

        (cycle_dir / "issues.json").write_text(
            json.dumps(
                {
                    "verify_issues": verify_issues,
                    "evaluate_issues": eval_issues,
                    "unresolved_issues": unresolved,
                    "verify_pass": verify_pass,
                    "evaluate_pass": eval_pass,
                },
                indent=2,
            ),
            encoding="utf-8",
        )

        print(
            f"[cycle {cycle}] issues={len(unresolved)} verify_pass={verify_pass} evaluate_pass={eval_pass}"
        )
        append_event(
            run_dir,
            f"cycle {cycle} finished with {len(unresolved)} issue(s), "
            f"verify_pass={verify_pass}, evaluate_pass={eval_pass}",
        )
        write_status_files(
            config=config,
            run_dir=run_dir,
            summary=summary,
            progress=progress,
            state="running",
        )

        if not unresolved and eval_pass:
            summary["completed"] = True
            summary["stopped_at_cycle"] = cycle
            append_event(run_dir, f"run converged at cycle {cycle}")
            break

    summary["ended_at"] = datetime.now().isoformat(timespec="seconds")
    if summary.get("completed"):
        append_event(run_dir, "run completed successfully")
    else:
        append_event(run_dir, "run stopped at max cycles with unresolved issues")
    finalize_run(
        config=config,
        run_dir=run_dir,
        summary=summary,
        task_prompt=task_prompt,
        evaluation_prompt=evaluation_prompt,
        current_plan=current_plan,
        progress=progress,
        state="completed" if summary.get("completed") else "incomplete",
    )

    print(f"Run completed. Artifacts: {run_dir}")
    if not summary.get("completed"):
        print("Run stopped at max cycles with unresolved issues.")

    return run_dir
