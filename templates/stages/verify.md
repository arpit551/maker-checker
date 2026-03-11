STAGE: verify
CYCLE: {cycle_index}

Verify whether execution satisfied the plan and list unresolved issues.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Revised Plan
{revise_output}

## Execution Report
{execute_output}

Return strict JSON only with this schema:
{{
  "pass": true or false,
  "issues": ["issue 1", "issue 2"],
  "notes": "short rationale"
}}

Use only the provided text context. Do not run shell commands or inspect files.
