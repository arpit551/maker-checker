# maker-checker

`maker-checker` runs a six-stage maker-checker loop:

1. Codex plans
2. Claude critiques
3. Codex revises
4. Claude executes
5. Codex verifies
6. Codex evaluates

The default user workflow is centered on a hidden project-local workspace at `.maker-checker/`. That folder holds the editable config, briefs, templates, run artifacts, and dashboard state.

## Install

One-line install from GitHub:

```bash
uv tool install git+https://github.com/arpit551/maker-checker.git
```

Alternative with `pipx`:

```bash
pipx install git+https://github.com/arpit551/maker-checker.git
```

Source install still works:

```bash
pip install .
```

## Commands

- `maker-checker init`
- `maker-checker run`
- `maker-checker dashboard`

Compatibility entrypoints also exist:

- `maker-checker-init`
- `maker-checker-dashboard`

## Quick Start

From any project directory:

```bash
maker-checker init
```

That creates:

- `.maker-checker/config.toml`
- `.maker-checker/briefs/task.md`
- `.maker-checker/briefs/evaluation.md`
- `.maker-checker/templates/stages/*.md`
- `.maker-checker/runs/`
- `.maker-checker/memory/`

Edit the local files in `.maker-checker/` as needed, then run:

```bash
maker-checker run
```

By default `maker-checker run` starts the dashboard and the workflow together. The dashboard is served on `http://127.0.0.1:8765` while the loop is running.

To run the workflow without the dashboard:

```bash
maker-checker run --no-dashboard
```

To serve the dashboard separately against the saved run state:

```bash
maker-checker dashboard
```

## Hidden Workspace Model

The package ships built-in default briefs and stage templates, but the intended override point is `.maker-checker/`.

`maker-checker init` copies all of these into `.maker-checker/` so users can edit them directly:

- `config.toml`
- task brief
- evaluation brief
- all stage templates

The generated config points at the local `.maker-checker/templates/stages/*.md` files, so edits there take effect immediately on the next run.

## Layout

Inside `.maker-checker/`:

- `config.toml`: local workflow config
- `briefs/task.md`: implementation brief
- `briefs/evaluation.md`: scoring rubric
- `templates/stages/*.md`: editable stage prompts
- `runs/latest_status.md`: latest live status in Markdown
- `runs/latest_status.json`: latest live status in JSON
- `runs/runtime_state.json`: stable dashboard/API state
- `runs/latest_summary.md`: latest run summary
- `memory/run_history.md`: human-readable cross-run memory
- `memory/run_history.jsonl`: structured cross-run memory

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

The dashboard UI is run-centric:

- each run is a collapsible card
- each open run exposes stage pills for `plan`, `critique`, `revise`, `execute`, `verify`, and `evaluate`
- tabs separate `Prompt`, `Logs`, `Output`, `Summary`, and `Live`
- the live view shows the current stage plus live logs when a run is active

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

- Default config path: `.maker-checker/config.toml`
- `input_mode = "stdin"` sends the rendered stage prompt via stdin
- `input_mode = "file"` injects `{prompt_file}` into the command
- Available placeholders: `{prompt_file}`, `{output_file}`, `{stage_dir}`, `{session_id}`
- The default scaffold expects working `codex` and `claude` CLIs with valid authentication
- If you do not want local template overrides, you can remove `template_file` entries and fall back to the package defaults
