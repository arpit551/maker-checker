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
- Inspect the repository and runtime state as needed. Ground decisions in what you actually observe.
- Resolve cheap local prerequisites directly when safe: start a local service, rerun a health check, clear app state, or pass explicit CLI flags derived from observed facts.
- Before declaring credentials or configuration missing, inspect the supported loading path (`.env`, config file, CLI defaults, process environment) without revealing secret values.
- If a prerequisite is still unavailable after a direct check, stop quickly and report the blocker, commands run, and the exact missing dependency instead of pretending execution succeeded.
- Honor any explicit verification command or event/time budget from the evaluation brief unless a broader reproduction is clearly needed first.
- Use bounded baseline and verification runs whenever they are enough to diagnose the issue; do not default to the largest available config budget unless the failure only appears there.
- If correctness depends on current documentation, APIs, or external facts, check them during execution and name the sources you used.
- Keep research summaries short and only include facts that changed the work.
- Never claim a file change, command, test, benchmark, source review, or runtime result that did not actually happen.
- If a command fails or evidence is incomplete, report that directly instead of smoothing it over.

## Output Requirements
- Use sections: Research, Completed, Commands run, Files changed, Verification, Remaining concerns.
- In `Research`, list the sources checked or write `none`.
- Be factual and explicit about what did and did not happen.
- Do not invent repository facts, hidden requirements, or completed work.
- If the task brief forbids edits or commands, produce a dry-run execution summary and do not change files.
