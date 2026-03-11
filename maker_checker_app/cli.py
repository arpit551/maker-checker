from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config
from .models import WorkflowError
from .runtime import run_workflow


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Looped maker-checker orchestrator for Codex + Claude workflows."
    )
    parser.add_argument("--config", default="config.toml", help="Path to workflow config TOML.")
    parser.add_argument("--task-file", help="Override task brief file.")
    parser.add_argument("--evaluation-file", help="Override evaluation brief file.")
    parser.add_argument("--max-cycles", type=int, help="Override max cycles from config.")
    parser.add_argument("--run-name", help="Optional run name suffix.")
    parser.add_argument(
        "--history-limit",
        type=int,
        help="Override how many recent runs are injected into the next run context.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    try:
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

        run_workflow(config=config, run_name=args.run_name)
        return 0
    except WorkflowError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
