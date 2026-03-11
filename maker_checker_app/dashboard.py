from __future__ import annotations

import argparse
from datetime import datetime
import json
import mimetypes
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import parse_qs, unquote, urlparse

from .config import get_history_dir, load_config
from .models import DEFAULT_CONFIG_FILE, REQUIRED_STAGES, STATE_SCHEMA_VERSION, WorkflowConfig
from .runtime import build_status_payload, init_progress, load_history_entries


STATIC_DIR = Path(__file__).resolve().parent / "dashboard_static"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Serve the local maker-checker dashboard.")
    parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Path to workflow config TOML.")
    parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    parser.add_argument("--port", type=int, default=8765, help="Port to bind.")
    return parser.parse_args()


def read_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8")


def build_idle_run_detail(config: WorkflowConfig) -> dict:
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": None,
        "state": "idle",
        "active_cycle": None,
        "active_stage": None,
        "next_stage": None,
        "started_at": None,
        "ended_at": None,
        "updated_at": None,
        "stage_position": {"completed": 0, "total": 0},
        "evaluation_state": {
            "verify_pass": None,
            "evaluate_pass": None,
            "issues_count": 0,
            "issues": [],
        },
        "attempts": {"current": 0, "max": config.max_cycles, "started_reason": None, "next": None},
        "retry": None,
        "runtime_totals": {
            "seconds_running": 0.0,
            "tokens": {
                "input_tokens": 0,
                "output_tokens": 0,
                "total_tokens": 0,
                "reported_stage_count": 0,
                "available": False,
            },
        },
        "latest_outputs": {},
        "current_session": None,
        "what_happened": [],
        "what_is_happening": "No run activity yet.",
        "what_happens_next": "Start a run to populate the dashboard.",
        "cycles": [],
        "recent_events": [],
        "summary_markdown": "No summary yet.",
        "history_file": str(get_history_dir(config) / "run_history.md"),
        "task_brief_path": str(config.task_prompt_file),
        "evaluation_brief_path": str(config.evaluation_prompt_file),
        "run_summary_file": None,
        "status_file": None,
        "last_event": None,
        "last_error": None,
        "latest_change": None,
    }


def list_runs(config: WorkflowConfig) -> list[dict[str, object]]:
    runs: list[dict[str, object]] = []
    if not config.artifacts_dir.exists():
        return runs

    for path in sorted(config.artifacts_dir.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        status = load_run_detail(config, path.name)
        evaluation = status.get("evaluation_state", {})
        runtime_totals = status.get("runtime_totals", {})
        runs.append(
            {
                "schema_version": status.get("schema_version", STATE_SCHEMA_VERSION),
                "run_id": path.name,
                "state": status.get("state") or ("completed" if status.get("completed") else "incomplete"),
                "started_at": status.get("started_at"),
                "updated_at": status.get("updated_at") or status.get("ended_at"),
                "active_cycle": status.get("active_cycle"),
                "active_stage": status.get("active_stage"),
                "issues_count": evaluation.get("issues_count", 0),
                "last_error": status.get("last_error"),
                "last_event": status.get("last_event"),
                "seconds_running": runtime_totals.get("seconds_running", 0.0),
            }
        )
    return runs


def _load_status_seed(run_dir: Path) -> dict:
    status_path = run_dir / "status.json"
    summary_path = run_dir / "summary.json"
    if status_path.exists():
        return json.loads(status_path.read_text(encoding="utf-8"))
    if summary_path.exists():
        return json.loads(summary_path.read_text(encoding="utf-8"))
    return {}


def _resolve_default_run_id(config: WorkflowConfig) -> str | None:
    if not config.artifacts_dir.exists():
        return None

    fallback: str | None = None
    for path in sorted(config.artifacts_dir.iterdir(), reverse=True):
        if not path.is_dir():
            continue
        fallback = fallback or path.name
        seed = _load_status_seed(path)
        if seed.get("state") == "running":
            return path.name
    return fallback


def _rebuild_live_run_detail(config: WorkflowConfig, run_dir: Path, seed: dict) -> dict:
    if not seed:
        return build_idle_run_detail(config)

    max_cycles = int(seed.get("max_cycles", config.max_cycles))
    progress = init_progress(max_cycles)
    for cycle_record in seed.get("cycles", []):
        cycle_number = int(cycle_record.get("cycle", 0))
        if cycle_number not in progress:
            continue
        for stage_name, state in (cycle_record.get("stages") or {}).items():
            if stage_name in progress[cycle_number]:
                progress[cycle_number][stage_name] = state

    summary = {
        "started_at": seed.get("started_at"),
        "ended_at": seed.get("ended_at"),
        "cycles": seed.get("cycles", []),
        "completed": seed.get("state") == "completed",
        "failure": seed.get("failure"),
        "history_loaded": seed.get("history_loaded", False),
        "workspace": seed.get("workspace"),
    }
    detail = build_status_payload(
        config=config,
        run_dir=run_dir,
        summary=summary,
        progress=progress,
        state=seed.get("state", "idle"),
        active_cycle=seed.get("active_cycle"),
        active_stage=seed.get("active_stage"),
    )
    detail["updated_at"] = datetime.now().isoformat(timespec="seconds")
    return detail


def load_run_detail(config: WorkflowConfig, run_id: str | None) -> dict:
    if run_id is None:
        run_id = _resolve_default_run_id(config)
    run_dir = config.artifacts_dir / run_id if run_id else None
    if run_dir is None or not run_dir.exists():
        return build_idle_run_detail(config)

    seed = _load_status_seed(run_dir)
    if not seed:
        return build_idle_run_detail(config)

    detail = _rebuild_live_run_detail(config, run_dir, seed)
    summary_path = run_dir / "run_summary.md"
    detail["summary_markdown"] = read_text(summary_path) or "No summary yet."
    return detail


def load_status(config: WorkflowConfig, run_id: str | None) -> dict:
    return load_run_detail(config, run_id)


def load_history(config: WorkflowConfig, limit: int = 8) -> list[dict]:
    return load_history_entries(get_history_dir(config))[-limit:][::-1]


def select_current_run_id(runs: list[dict[str, object]]) -> str | None:
    running = next((run for run in runs if run.get("state") == "running"), None)
    if running:
        return str(running["run_id"])
    if runs:
        return str(runs[0]["run_id"])
    return None


def load_runtime_state(config: WorkflowConfig) -> dict:
    path = config.artifacts_dir / "runtime_state.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass

    runs = list_runs(config)
    current_run_id = select_current_run_id(runs)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_run_id": current_run_id,
        "current_run_state": runs[0]["state"] if runs else "idle",
        "current_run_path": str(config.artifacts_dir / current_run_id) if current_run_id else None,
        "current_run": load_run_detail(config, current_run_id),
    }


def build_state_payload(config: WorkflowConfig) -> dict:
    runs = list_runs(config)
    runtime_state = load_runtime_state(config)
    current_run_id = select_current_run_id(runs) or runtime_state.get("current_run_id")
    current_run = load_run_detail(config, current_run_id)
    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "current_run_id": current_run_id,
        "current_run": current_run,
        "runs": runs,
        "history": load_history(config),
    }


def load_summary_text(config: WorkflowConfig, run_id: str | None) -> str:
    return load_run_detail(config, run_id).get("summary_markdown", "No summary yet.")


def get_stage_dir(run_dir: Path, cycle: int, stage_name: str) -> Path:
    step_index = REQUIRED_STAGES.index(stage_name) + 1
    return run_dir / f"cycle-{cycle:02d}" / f"{step_index:02d}-{stage_name}"


def read_stage_log_file(path: Path, limit: int | None = None) -> str:
    text = read_text(path)
    if limit is not None and limit > 0 and len(text) > limit:
        return text[-limit:]
    return text


def resolve_stage_context(config: WorkflowConfig, run_id: str, cycle: int | None, stage_name: str) -> tuple[dict, dict | None, dict | None, Path]:
    if stage_name not in REQUIRED_STAGES:
        raise ValueError(stage_name)

    run_dir = config.artifacts_dir / run_id
    if not run_dir.exists():
        raise FileNotFoundError(run_id)

    detail = load_run_detail(config, run_id)
    if cycle is None:
        cycle = detail.get("active_cycle") or (detail.get("cycles", [{}])[-1].get("cycle") if detail.get("cycles") else None)
    if cycle is None:
        raise FileNotFoundError("cycle")

    cycle_record = next((item for item in detail.get("cycles", []) if item.get("cycle") == int(cycle)), None)
    if cycle_record is None:
        raise FileNotFoundError("cycle")
    stage_record = next((item for item in cycle_record.get("stage_details", []) if item.get("stage") == stage_name), None)
    if stage_record is None:
        raise FileNotFoundError(stage_name)

    stage_dir = get_stage_dir(run_dir, int(cycle), stage_name)
    return detail, cycle_record, stage_record, stage_dir


def load_stage_logs(
    config: WorkflowConfig,
    run_id: str,
    cycle: int | None,
    stage_name: str,
    limit: int | None = None,
) -> dict:
    detail, _, stage_record, stage_dir = resolve_stage_context(config, run_id, cycle, stage_name)
    stream_files = {
        "assistant_output": stage_dir / "assistant_output.txt",
        "stdout": stage_dir / "stdout.txt",
        "stderr": stage_dir / "stderr.txt",
        "combined": stage_dir / "combined.log",
    }
    streams: dict[str, dict[str, object]] = {}
    for stream_name, path in stream_files.items():
        streams[stream_name] = {
            "path": str(path),
            "exists": path.exists(),
            "text": read_stage_log_file(path, limit=limit),
            "bytes": path.stat().st_size if path.exists() else 0,
        }

    cycle_value = stage_record["cycle"]
    return {
        "run_id": run_id,
        "cycle": cycle_value,
        "stage": stage_name,
        "status": stage_record.get("status"),
        "agent": stage_record.get("agent"),
        "session_id": stage_record.get("session_id"),
        "reported_session_id": stage_record.get("reported_session_id"),
        "active": detail.get("active_cycle") == cycle_value and detail.get("active_stage") == stage_name,
        "paths": {name: data["path"] for name, data in streams.items()},
        "streams": streams,
        "updated_at": datetime.now().isoformat(timespec="seconds"),
    }


def load_stage_detail(
    config: WorkflowConfig,
    run_id: str,
    cycle: int | None,
    stage_name: str,
) -> dict:
    detail, cycle_record, stage_record, stage_dir = resolve_stage_context(config, run_id, cycle, stage_name)
    prompt_path = next(iter(sorted(stage_dir.glob("prompt*"))), None)
    assistant_output = read_text(stage_dir / "assistant_output.txt")
    stdout_text = read_text(stage_dir / "stdout.txt")
    stderr_text = read_text(stage_dir / "stderr.txt")
    prompt_text = read_text(prompt_path) if prompt_path is not None else ""
    combined_text = read_text(stage_dir / "combined.log")
    primary_output = assistant_output or stdout_text or stderr_text

    return {
        "schema_version": STATE_SCHEMA_VERSION,
        "run_id": run_id,
        "cycle": cycle_record["cycle"],
        "stage": stage_name,
        "status": stage_record.get("status"),
        "agent": stage_record.get("agent"),
        "session_id": stage_record.get("session_id"),
        "reported_session_id": stage_record.get("reported_session_id"),
        "display_session_id": stage_record.get("display_session_id"),
        "started_at": stage_record.get("started_at"),
        "ended_at": stage_record.get("ended_at"),
        "elapsed_sec": stage_record.get("elapsed_sec"),
        "command": stage_record.get("command"),
        "last_error": stage_record.get("last_error"),
        "exit_code": stage_record.get("exit_code"),
        "tokens": stage_record.get("tokens", {}),
        "paths": {
            "prompt": str(prompt_path) if prompt_path is not None else None,
            "assistant_output": str(stage_dir / "assistant_output.txt"),
            "stdout": str(stage_dir / "stdout.txt"),
            "stderr": str(stage_dir / "stderr.txt"),
            "combined": str(stage_dir / "combined.log"),
        },
        "content": {
            "prompt": prompt_text,
            "assistant_output": assistant_output,
            "stdout": stdout_text,
            "stderr": stderr_text,
            "combined": combined_text,
            "primary_output": primary_output,
        },
        "active": detail.get("active_cycle") == cycle_record["cycle"] and detail.get("active_stage") == stage_name,
    }


def _json_error(code: str, message: str) -> dict:
    return {"error": {"code": code, "message": message}}


def _static_path(request_path: str) -> Path | None:
    if request_path in {"/", "/index.html"}:
        return STATIC_DIR / "index.html"
    if request_path.startswith("/static/"):
        relative = request_path.removeprefix("/static/")
        candidate = (STATIC_DIR / relative).resolve()
        if STATIC_DIR.resolve() not in candidate.parents and candidate != STATIC_DIR.resolve():
            return None
        return candidate
    return None


def make_handler(config: WorkflowConfig):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args) -> None:  # noqa: A003
            return

        def _send(self, body: bytes, content_type: str, status: int = 200) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_json(self, payload: object, status: int = 200) -> None:
            self._send(json.dumps(payload).encode("utf-8"), "application/json; charset=utf-8", status=status)

        def _send_file(self, path: Path) -> None:
            if not path.exists() or not path.is_file():
                self._send_json(_json_error("not_found", "Asset not found"), status=404)
                return
            mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
            self._send(path.read_bytes(), f"{mime}; charset=utf-8" if mime.startswith("text/") or mime == "application/javascript" else mime)

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            run_id = params.get("run", [None])[0]
            cycle_param = params.get("cycle", [None])[0]
            limit_param = params.get("limit", [None])[0]

            static_path = _static_path(parsed.path)
            if static_path is not None:
                self._send_file(static_path)
                return

            if parsed.path == "/api/v1/state":
                self._send_json(build_state_payload(config))
                return
            if parsed.path == "/api/v1/runs":
                self._send_json(list_runs(config))
                return
            if parsed.path == "/api/v1/history":
                self._send_json(load_history(config))
                return
            if parsed.path.startswith("/api/v1/runs/"):
                suffix = unquote(parsed.path.removeprefix("/api/v1/runs/"))
                try:
                    cycle_value = int(cycle_param) if cycle_param is not None else None
                except ValueError:
                    self._send_json(_json_error("invalid_cycle", "cycle must be an integer"), status=400)
                    return
                try:
                    limit_value = int(limit_param) if limit_param is not None else None
                except ValueError:
                    self._send_json(_json_error("invalid_limit", "limit must be an integer"), status=400)
                    return

                if "/stages/" in suffix:
                    requested_run_id, stage_suffix = suffix.split("/stages/", 1)
                    if not (config.artifacts_dir / requested_run_id).exists():
                        self._send_json(_json_error("not_found", "Run not found"), status=404)
                        return
                    if stage_suffix.endswith("/logs"):
                        requested_stage = stage_suffix.removesuffix("/logs")
                        try:
                            self._send_json(load_stage_logs(config, requested_run_id, cycle_value, requested_stage, limit_value))
                        except FileNotFoundError:
                            self._send_json(_json_error("not_found", "Stage logs not found"), status=404)
                        except ValueError:
                            self._send_json(_json_error("invalid_stage", "Unknown stage"), status=400)
                        return

                    requested_stage = stage_suffix.rstrip("/")
                    try:
                        self._send_json(load_stage_detail(config, requested_run_id, cycle_value, requested_stage))
                    except FileNotFoundError:
                        self._send_json(_json_error("not_found", "Stage detail not found"), status=404)
                    except ValueError:
                        self._send_json(_json_error("invalid_stage", "Unknown stage"), status=400)
                    return

                if suffix.endswith("/summary"):
                    requested_run_id = suffix.removesuffix("/summary")
                    if not (config.artifacts_dir / requested_run_id).exists():
                        self._send_json(_json_error("not_found", "Run not found"), status=404)
                        return
                    self._send(load_summary_text(config, requested_run_id).encode("utf-8"), "text/plain; charset=utf-8")
                    return

                if not (config.artifacts_dir / suffix).exists():
                    self._send_json(_json_error("not_found", "Run not found"), status=404)
                    return
                self._send_json(load_run_detail(config, suffix))
                return

            if parsed.path == "/api/runs":
                self._send_json(list_runs(config))
                return
            if parsed.path == "/api/status":
                self._send_json(load_status(config, run_id))
                return
            if parsed.path == "/api/history":
                self._send_json(load_history(config))
                return
            if parsed.path == "/api/summary":
                self._send(load_summary_text(config, run_id).encode("utf-8"), "text/plain; charset=utf-8")
                return

            self._send_json(_json_error("not_found", "Not found"), status=404)

    return Handler


def create_server(config: WorkflowConfig, host: str, port: int) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((host, port), make_handler(config))


def start_server_in_background(config: WorkflowConfig, host: str, port: int) -> tuple[ThreadingHTTPServer, Thread]:
    server = create_server(config, host, port)
    thread = Thread(target=server.serve_forever, daemon=True, name="maker-checker-dashboard")
    thread.start()
    return server, thread


def main() -> int:
    args = parse_args()
    config = load_config(Path(args.config).expanduser().resolve())
    server = create_server(config, args.host, args.port)
    print(f"Dashboard running at http://{args.host}:{args.port}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
