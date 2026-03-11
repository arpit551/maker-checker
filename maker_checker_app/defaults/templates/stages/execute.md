STAGE: execute
CYCLE: {cycle_index}

Execute the revised plan in the repository and report what happened.
You are rewarded for doing the real work, verifying facts before acting, and surfacing uncertainty early.
You are penalized for pretending work happened, hiding failed commands, or relying on stale docs or stale research.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Revised Plan
{revise_output}

## Execution Rules
- Follow the revised plan, but adapt if new evidence shows a safer or more correct path.
- When the task depends on unfamiliar or fast-moving APIs, libraries, security guidance, or research claims, do targeted research before editing.
- If your environment supports it, use sub-agents in parallel for bounded research or validation tasks.
- Prefer official docs, source code, standards, and recent papers over tertiary summaries.
- Distill research into only the facts needed for the task; do not paste large summaries.
- Never claim a file change, command, test, benchmark, or source review that did not actually happen.

## Output Requirements
- Use sections: Research, Completed, Commands run, Files changed, Verification, Remaining concerns.
- In `Research`, list the sources checked or write `none`.
- Be factual and explicit about what did and did not happen.
- Do not invent repository facts, hidden requirements, or completed work.
- If the task brief forbids edits or commands, produce a dry-run execution summary and do not change files.
