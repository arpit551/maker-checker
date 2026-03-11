from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .bootstrap import init_workspace
from .config import load_config
from .dashboard import main as dashboard_main
from .dashboard import start_server_in_background
from .models import DEFAULT_CONFIG_FILE, WorkflowError
from .runtime import run_workflow


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] not in {"init", "run", "dashboard"}:
        argv = ["run", *argv]

    parser = argparse.ArgumentParser(
        description="Looped maker-checker orchestrator for Codex + Claude workflows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Create a .maker-checker workspace in the current project.",
    )
    init_parser.add_argument(
        "directory",
        nargs="?",
        default=".",
        help="Project directory where .maker-checker should be created.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing managed files inside .maker-checker.",
    )

    run_parser = subparsers.add_parser(
        "run",
        help="Run the maker-checker loop.",
    )
    run_parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Path to workflow config TOML.")
    run_parser.add_argument("--task-file", help="Override task brief file.")
    run_parser.add_argument("--evaluation-file", help="Override evaluation brief file.")
    run_parser.add_argument("--max-cycles", type=int, help="Override max cycles from config.")
    run_parser.add_argument("--run-name", help="Optional run name suffix.")
    run_parser.add_argument(
        "--history-limit",
        type=int,
        help="Override how many recent runs are injected into the next run context.",
    )
    run_parser.add_argument(
        "--dashboard",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="Start the dashboard while the workflow runs.",
    )
    run_parser.add_argument("--dashboard-host", default="127.0.0.1", help="Dashboard host.")
    run_parser.add_argument("--dashboard-port", type=int, default=8765, help="Dashboard port.")

    dashboard_parser = subparsers.add_parser(
        "dashboard",
        help="Serve the local dashboard.",
    )
    dashboard_parser.add_argument("--config", default=DEFAULT_CONFIG_FILE, help="Path to workflow config TOML.")
    dashboard_parser.add_argument("--host", default="127.0.0.1", help="Host to bind.")
    dashboard_parser.add_argument("--port", type=int, default=8765, help="Port to bind.")

    return parser.parse_args(argv)


def _load_run_config(args: argparse.Namespace):
    config = load_config(Path(args.config).expanduser().resolve())

    if args.task_file:
        config.task_prompt_file = Path(args.task_file).expanduser().resolve()
    if args.evaluation_file:
        config.evaluation_prompt_file = Path(args.evaluation_file).expanduser().resolve()
    if args.max_cycles is not None:
        if args.max_cycles < 1:
            raise WorkflowError("--max-cycles must be >= 1")
        config.max_cycles = args.max_cycles
    if args.history_limit is not None:
        if args.history_limit < 1:
            raise WorkflowError("--history-limit must be >= 1")
        config.history_limit = args.history_limit

    return config


def main() -> int:
    args = parse_args()

    try:
        if args.command == "init":
            created = init_workspace(Path(args.directory), force=args.force)
            print("Created maker-checker workspace:")
            for path in created:
                print(f"- {path}")
            return 0

        if args.command == "dashboard":
            dashboard_argv = [
                "--config",
                args.config,
                "--host",
                args.host,
                "--port",
                str(args.port),
            ]
            with _patched_argv(["maker-checker-dashboard", *dashboard_argv]):
                return dashboard_main()

        config = _load_run_config(args)
        server = None
        if args.dashboard:
            try:
                server, _thread = start_server_in_background(
                    config,
                    args.dashboard_host,
                    args.dashboard_port,
                )
            except OSError as exc:
                raise WorkflowError(
                    f"Could not start dashboard on {args.dashboard_host}:{args.dashboard_port}: {exc}"
                ) from exc
            print(f"Dashboard running at http://{args.dashboard_host}:{args.dashboard_port}")

        try:
            run_workflow(config=config, run_name=args.run_name)
        finally:
            if server is not None:
                server.shutdown()
                server.server_close()
        return 0
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


class _patched_argv:
    def __init__(self, argv: list[str]) -> None:
        self.argv = argv
        self.previous: list[str] | None = None

    def __enter__(self) -> None:
        self.previous = sys.argv[:]
        sys.argv = self.argv

    def __exit__(self, exc_type, exc, tb) -> None:
        if self.previous is not None:
            sys.argv = self.previous
