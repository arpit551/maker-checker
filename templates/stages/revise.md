STAGE: revise
CYCLE: {cycle_index}

Revise the plan using the critique and recent run memory.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Current Plan
{plan_output}

## Claude Critique
{critique_output}

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Steps, Risks, Success checks.
- Address critique items explicitly.
- Remove invented assumptions rather than doubling down on them.
- Do not run shell commands or inspect repository state while revising.
