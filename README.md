# maker-checker

`maker-checker` runs a seven-stage maker-checker loop:

1. Codex discovers grounded repo/runtime facts
2. Codex plans
3. Claude critiques
4. Codex revises
5. Claude executes
6. Codex verifies
7. Codex evaluates

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

By default the workflow runs in a disposable git worktree, not in your main checkout.
Each run gets its own branch and working directory under `.maker-checker/worktrees/`.

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
The package defaults under `maker_checker_app/defaults/` are the seed source of truth; there is no separate repo-root scaffold to maintain anymore.

## Git Isolation

The default execution mode is git-isolated:

- `maker-checker run` creates a dedicated branch and worktree for that run
- all stage commands execute inside that worktree
- the main checkout stays untouched while the loop is running
- each cycle is checkpointed inside the run branch
- if a later cycle clearly regresses, the runner resets the worktree back to the last accepted checkpoint
- fresh workspaces also default to `git.apply_on_success = true`, which safely applies successful changes back to the base checkout only when that checkout is still clean and unchanged since the run started

This means the loop can iterate aggressively without repeatedly dirtying your main branch.

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
- `memory/run_history.md`: human-readable carry-forward notes
- `memory/run_history.jsonl`: structured carry-forward notes
- `worktrees/<run-id>/`: disposable per-run git worktrees

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
- each open run exposes stage pills for `discover`, `plan`, `critique`, `revise`, `execute`, `verify`, and `evaluate`
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
- Default history window: the latest 2 runs, rendered as compact carry-forward notes
- Default git mode: isolated `worktree`
- `maker-checker run` expects to be inside a git repository with a committed `HEAD`
- `input_mode = "stdin"` sends the rendered stage prompt via stdin
- `input_mode = "file"` injects `{prompt_file}` into the command
- Available placeholders: `{prompt_file}`, `{output_file}`, `{stage_dir}`, `{session_id}`
- The default scaffold expects working `codex` and `claude` CLIs with valid authentication
- If you do not want local template overrides, you can remove `template_file` entries and fall back to the package defaults
