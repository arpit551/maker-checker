# maker-checker orchestrator

This repo runs a maker-checker loop:

1. Codex plans.
2. Claude critiques.
3. Codex revises.
4. Claude executes.
5. Codex verifies.
6. Codex evaluates.
7. The next cycle reuses unresolved issues plus recent run history.

The repo is organized around markdown briefs and markdown templates instead of raw text prompt files.
It now has a single execution mode: real Codex + Claude runs.

## Layout

- `/Users/arpit/projects/maker-checker/briefs/task.md`: the task brief you want the loop to work on
- `/Users/arpit/projects/maker-checker/briefs/evaluation.md`: the rubric used to judge the result
- `/Users/arpit/projects/maker-checker/templates/stages/*.md`: internal stage templates
- `/Users/arpit/projects/maker-checker/memory/run_history.md`: reusable lessons from past runs
- `/Users/arpit/projects/maker-checker/runs/latest_status.md`: live status dashboard for the newest run
- `/Users/arpit/projects/maker-checker/runs/latest_status.json`: live machine-readable status for the newest run
- `/Users/arpit/projects/maker-checker/runs/latest_summary.md`: final summary for the newest run

## Code Structure

- `/Users/arpit/projects/maker-checker/maker_checker.py`: thin entrypoint and compatibility wrapper
- `/Users/arpit/projects/maker-checker/maker_checker_app/models.py`: constants, dataclasses, and shared error types
- `/Users/arpit/projects/maker-checker/maker_checker_app/config.py`: config loading and path resolution
- `/Users/arpit/projects/maker-checker/maker_checker_app/text.py`: prompt rendering and assessment parsing helpers
- `/Users/arpit/projects/maker-checker/maker_checker_app/runtime.py`: run execution, reporting, and run-history updates
- `/Users/arpit/projects/maker-checker/maker_checker_app/cli.py`: CLI argument handling
- `/Users/arpit/projects/maker-checker/maker_checker_app/dashboard.py`: local web dashboard server
- `/Users/arpit/projects/maker-checker/dashboard.py`: thin dashboard entrypoint

## What You See Per Run

Each run now writes both machine and human-friendly artifacts:

- `summary.json`: structured run data
- `status.md`: live progress view with cycle/stage status
- `status.json`: live API-friendly view with active stage, next stage, evaluation state, stage snapshots, and event log tail
- `run_summary.md`: short human summary of what improved, what failed, and what to reuse next run
- `task_brief.md` and `evaluation_brief.md`: copies of the exact briefs used
- `final_plan.md`: the last plan generated in the loop
- `events.log`: timestamped runtime log for the run

## Quick Start

Run the workflow:

```bash
cd /Users/arpit/projects/maker-checker
python3 maker_checker.py \
  --config config.toml \
  --task-file briefs/task.md \
  --evaluation-file briefs/evaluation.md \
  --max-cycles 3
```

Run the live dashboard:

```bash
python3 dashboard.py --config config.toml --port 8765
```

Then open `http://127.0.0.1:8765`.

## Notes

- `input_mode = "stdin"` sends the rendered stage prompt via stdin.
- `input_mode = "file"` injects `{prompt_file}` into the command.
- Available placeholders: `{prompt_file}`, `{output_file}`, `{stage_dir}`, `{session_id}`.
- Recent run history is automatically injected into the next run context from `/Users/arpit/projects/maker-checker/memory/run_history.md`.
- The default config expects real `codex` and `claude` CLIs to be installed and authenticated.
- The stage templates no longer repeat model identity; they focus only on the task, constraints, and output contract.
