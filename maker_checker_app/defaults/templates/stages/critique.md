STAGE: critique
CYCLE: {cycle_index}

Critique the plan before execution.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Plan To Critique
{plan_output}

## Review Rules
- Use only the provided text context.
- Do not infer repository state, commit history, existing artifacts, prior logs, device state, or environment prerequisites unless they are explicitly present in the prompt.
- Focus on blocking issues: invented assumptions, missing verification, unsafe sequencing, missing rollback/safety steps, or ambiguity that would cause wasted execution.
- Prefer corrections that would materially change execution quality. Ignore style-only comments.
- If a critique point depends on information that was not provided, do not state it as fact.

## Output Requirements
- Return concise bullet points only.
- Call out invented assumptions, stale technical claims, skipped research, or missing verification.
- If there are no blocking issues, output exactly: NO_BLOCKING_ISSUES
