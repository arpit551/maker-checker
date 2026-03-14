STAGE: critique
CYCLE: {cycle_index}

Critique the plan before execution.

## Task Brief
{task_prompt}

## Evaluation Brief
{evaluation_prompt}

## Recent Run Memory
{recent_run_memory}

## Discovery Findings
{discover_output}

## Plan To Critique
{plan_output}

## Review Rules
- Use only the provided text context.
- Do not infer repository state, commit history, existing artifacts, prior logs, device state, or environment prerequisites unless they are explicitly present in the prompt.
- Focus on blocking issues: invented assumptions, missing verification, unsafe sequencing, missing rollback/safety steps, or ambiguity that would cause wasted execution.
- Flag plans that defer routine checks back to the user instead of resolving them directly during execution.
- Flag plans that ignore explicit verification commands, budgets, or artifact requirements from the evaluation brief without a clear reason.
- Flag plans that put the exact evaluation command or other full-budget validation work in `Execute:` steps when `Verify:` would be the appropriate place.
- Prefer corrections that would materially change execution quality. Ignore style-only comments.
- If a critique point depends on information that was not provided, do not state it as fact.
- Reference the specific step, section, or phrase you are critiquing.
- If something is unknown from the prompt, say `Unknown from provided context` instead of guessing.

## Output Requirements
- Return concise bullet points only.
- Call out invented assumptions, stale technical claims, skipped research, or missing verification.
- If there are no blocking issues, output exactly: NO_BLOCKING_ISSUES
