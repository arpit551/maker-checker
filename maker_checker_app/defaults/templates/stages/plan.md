STAGE: plan
CYCLE: {cycle_index}

Produce the next implementation plan.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Unresolved Issues From The Previous Cycle
{unresolved_issues_bulleted}

## Previous Plan
{previous_plan}

## Planning Rules
- Use only the provided text context.
- Do not invent repository facts, files, commits, logs, prior runs, test coverage, or environment state that were not provided.
- Start from the task brief, recent run memory, unresolved issues, and previous plan.
- If the next step depends on inspecting the repository, logs, runtime artifacts, or current docs, say exactly what should be checked during execution. Do not pretend that work already happened.
- Prefer the smallest maintainable path that can be verified clearly.
- Keep the plan concise and concrete. Do not restate the full brief.
- Call out unknowns and evidence needed instead of guessing.

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Research, Steps, Risks, Success checks.
- In `Research`, write `none` if no extra research is needed.
- Make the steps specific and ordered.
- Make the steps concrete enough that an executor or sub-agent could pick them up without guessing.
- If the task brief is ambiguous, make the first steps reduce ambiguity instead of inventing requirements.
