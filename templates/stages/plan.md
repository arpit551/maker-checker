STAGE: plan
CYCLE: {cycle_index}

Generate the next implementation plan.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Unresolved Issues From The Previous Cycle
{unresolved_issues_bulleted}

## Previous Plan
{previous_plan}

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Steps, Risks, Success checks.
- Make the steps specific and ordered.
- If the task brief is ambiguous, make the first steps about clarifying scope instead of inventing requirements.
- Do not run shell commands or inspect repository state while planning.
