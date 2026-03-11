STAGE: critique
CYCLE: {cycle_index}

Critique the plan before execution.
You are rewarded for catching missing research, hidden assumptions, weak sequencing, and missing verification.
You are penalized for generic style feedback, minor wording nits, or criticism that would not change execution quality.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Plan To Critique
{plan_output}

## Review Rules
- Check whether the plan is grounded in the task brief, recent run memory, and unresolved issues.
- Check whether the plan schedules research when freshness, current docs, or recent papers materially affect correctness.
- Check whether the work is decomposed enough that bounded sub-agent work could run safely in parallel when available.
- Check for missing tests, missing rollback or safety steps, and missing verification evidence.
- Prefer blocking feedback over editorial advice.

## Output Requirements
- Return concise bullet points only.
- Call out invented assumptions, stale technical claims, skipped research, or missing verification.
- If there are no blocking issues, output exactly: NO_BLOCKING_ISSUES
