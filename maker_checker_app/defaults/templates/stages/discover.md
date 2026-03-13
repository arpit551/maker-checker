STAGE: discover
CYCLE: {cycle_index}

Inspect the available repository, runtime, and artifact context before planning.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Unresolved Issues From The Previous Cycle
{unresolved_issues_bulleted}

## Previous Plan
{previous_plan}

## Discovery Rules
- Ground every finding in what you actually inspect during this stage.
- Prefer concrete evidence over interpretation: files, code paths, config entries, logs, artifacts, command output.
- If something is unknown, say `Unknown` instead of guessing.
- Focus on the facts that will change the plan, execution risk, or verification strategy.
- Keep the output compact. This is a discovery note, not an essay.

## Output Requirements
- Return Markdown only.
- Include sections: Facts, Open questions, Recommended focus.
- In `Facts`, use short bullet points with evidence-backed observations only.
- In `Open questions`, list the most important unknowns or blockers.
- In `Recommended focus`, name the 1-3 highest-leverage areas the planner should act on next.
