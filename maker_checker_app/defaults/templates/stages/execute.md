STAGE: execute
CYCLE: {cycle_index}

Execute the revised plan in the repository and report what happened.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Revised Plan
{revise_output}

## Output Requirements
- Use sections: Completed, Commands run, Files changed, Remaining concerns.
- Be factual and explicit about what did and did not happen.
- Do not invent repository facts, hidden requirements, or completed work.
- If the task brief forbids edits or commands, produce a dry-run execution summary and do not change files.
