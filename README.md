# maker-checker

`maker-checker` runs a maker-checker loop across six stages:

1. Codex plans.
2. Claude critiques.
3. Codex revises.
4. Claude executes.
5. Codex verifies.
6. Codex evaluates.

Each run records artifacts, carry-forward history, and a live dashboard view so the next cycle can reuse what already worked and avoid repeating known failures.

## Install

Install from source:

```bash
pip install .
```

Or build a wheel first:

```bash
uv build --wheel
pip install dist/maker_checker-0.1.0-py3-none-any.whl
```

Installed commands:

- `maker-checker`: run the workflow
- `maker-checker-dashboard`: serve the local dashboard
- `maker-checker-init`: scaffold a workspace with config and briefs

The source-tree entrypoints `python3 maker_checker.py` and `python3 dashboard.py` still work when you are running directly from a checkout.

## Quick Start

Create a workspace:

```bash
mkdir my-maker-checker
cd my-maker-checker
maker-checker-init
```

That creates:

- `config.toml`
- `briefs/task.md`
- `briefs/evaluation.md`
- `runs/`
- `memory/`

Edit the briefs for your task, then run:

```bash
maker-checker --config config.toml
```

Start the dashboard:

```bash
maker-checker-dashboard --config config.toml --port 8765
```

Then open [http://127.0.0.1:8765](http://127.0.0.1:8765).

## Config Model

The generated `config.toml` keeps user-owned files local to the workspace and uses packaged stage templates by default. You only need to configure:

- workflow directories and cycle count
- task and evaluation briefs
- agent commands
- which agent owns each stage

You can still override any stage template with `template_file = "path/to/template.md"` if you want custom prompts for a specific installation.

## Workspace Layout

- `briefs/task.md`: the implementation brief
- `briefs/evaluation.md`: the scoring rubric
- `runs/latest_status.md`: latest human-readable live status
- `runs/latest_status.json`: latest machine-readable live status
- `runs/runtime_state.json`: dashboard-friendly state payload
- `runs/latest_summary.md`: latest human summary
- `memory/run_history.md`: reusable lessons from earlier runs
- `memory/run_history.jsonl`: structured cross-run history

Each run directory also contains:

- `summary.json`
- `status.md`
- `status.json`
- `run_summary.md`
- `task_brief.md`
- `evaluation_brief.md`
- `final_plan.md`
- `events.log`
- per-stage `stdout.txt`, `stderr.txt`, `assistant_output.txt`, and `combined.log`

## Dashboard

The dashboard is backed by a versioned runtime API and a packaged static frontend.

The UI is run-centric:

- each run opens as a collapsible card
- each open run shows stage pills for `plan`, `critique`, `revise`, `execute`, `verify`, and `evaluate`
- tabs separate `Prompt`, `Logs`, `Output`, `Summary`, and `Live`
- the live tab shows current stage context plus live log output for active runs

API endpoints:

- `GET /api/v1/state`
- `GET /api/v1/runs`
- `GET /api/v1/runs/<run_id>`
- `GET /api/v1/runs/<run_id>/summary`
- `GET /api/v1/runs/<run_id>/stages/<stage>?cycle=<n>`
- `GET /api/v1/runs/<run_id>/stages/<stage>/logs?cycle=<n>`
- `GET /api/v1/history`

Compatibility aliases under `/api/*` still exist.

## Notes

- `input_mode = "stdin"` sends the rendered stage prompt via stdin.
- `input_mode = "file"` injects `{prompt_file}` into the command.
- Available placeholders: `{prompt_file}`, `{output_file}`, `{stage_dir}`, `{session_id}`.
- Recent run history is injected from `memory/run_history.md`.
- The default scaffold expects working `codex` and `claude` CLIs with authentication already set up.
- Internal stage templates ship inside the package, so you do not need to copy `templates/` into every workspace.
