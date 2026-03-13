STAGE: execute
CYCLE: {cycle_index}

Execute the revised plan in the repository and report what happened.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Revised Plan
{revise_output}

## Execution Rules
- Follow the revised plan, but adapt if new evidence shows a safer or more correct path.
- Inspect the repository and runtime state as needed. Ground decisions in what you actually observe.
- If correctness depends on current documentation, APIs, or external facts, check them during execution and name the sources you used.
- Keep research summaries short and only include facts that changed the work.
- Never claim a file change, command, test, benchmark, source review, or runtime result that did not actually happen.

## Output Requirements
- Use sections: Research, Completed, Commands run, Files changed, Verification, Remaining concerns.
- In `Research`, list the sources checked or write `none`.
- Be factual and explicit about what did and did not happen.
- Do not invent repository facts, hidden requirements, or completed work.
- If the task brief forbids edits or commands, produce a dry-run execution summary and do not change files.
