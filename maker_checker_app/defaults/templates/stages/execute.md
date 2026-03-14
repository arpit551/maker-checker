STAGE: execute
CYCLE: {cycle_index}

Execute the revised plan in the repository and report what happened.

## Task Brief
{task_prompt}

## Evaluation Brief
{evaluation_prompt}

## Recent Run Memory
{recent_run_memory}

## Discovery Findings
{discover_output}

## Revised Plan
{revise_output}

## Execution Rules
- Follow the revised plan, but adapt if new evidence shows a safer or more correct path.
- Follow only plan steps labeled `Execute:`. Treat any `Verify:` steps as deferred work for the `verify` stage unless you must pull one forward to diagnose or de-risk the implementation.
- Inspect the repository and runtime state as needed. Ground decisions in what you actually observe.
- Treat the evaluation brief as the success target, not as an instruction to spend the full validation budget inside this stage when a smaller reproduction or smoke check is enough to implement safely.
- Resolve cheap local prerequisites directly when safe: start a local service, rerun a health check, clear app state, or pass explicit CLI flags derived from observed facts.
- When you need a language runtime or toolchain, prefer the repo-local command path (`.venv/bin/python`, `uv run`, package scripts, `python3`, etc.) instead of assuming generic commands like `python` exist on `PATH`.
- Before declaring credentials or configuration missing, inspect the supported loading path (`.env`, config file, CLI defaults, process environment) without revealing secret values.
- If a prerequisite is still unavailable after a direct check, stop quickly and report the blocker, commands run, and the exact missing dependency instead of pretending execution succeeded.
- Reproduce with the smallest command, fixture, or runtime path that is enough to confirm the bug and support a fix.
- Keep smoke checks short and implementation-focused. Leave the exact required validation command from the evaluation brief for the `verify` stage unless you need that broader run to diagnose the bug or to prove the implementation is safe before handing off.
- If you do spend substantial time on a broad validation run during execution, explain why the smaller reproduction was insufficient.
- If correctness depends on current documentation, APIs, or external facts, check them during execution and name the sources you used.
- Keep research summaries short and only include facts that changed the work.
- Never claim a file change, command, test, benchmark, source review, or runtime result that did not actually happen.
- If a command fails or evidence is incomplete, report that directly instead of smoothing it over.

## Output Requirements
- Use sections: Research, Completed, Commands run, Files changed, Verification, Remaining concerns.
- In `Research`, list the sources checked or write `none`.
- In `Verification`, separate implementation smoke checks from any broader validation that is being deferred to `verify`.
- Be factual and explicit about what did and did not happen.
- Do not invent repository facts, hidden requirements, or completed work.
- If the task brief forbids edits or commands, produce a dry-run execution summary and do not change files.
