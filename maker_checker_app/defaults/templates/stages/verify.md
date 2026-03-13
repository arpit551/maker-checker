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

## Verification Rules
- Check whether the execution report proves the revised plan actually happened.
- Treat missing evidence, skipped validation, stale-source claims, and "should work" language as issues.
- If the plan required research, confirm the execution report named concrete sources or explained why none were needed.
- Use only the provided text context. Do not run shell commands or inspect files.
- Do not assume success from confident language alone.
- If the evidence is incomplete, fail the verification and say what is missing.

Return strict JSON only with this schema:
{{
  "pass": true or false,
  "issues": ["issue 1", "issue 2"],
  "notes": "short rationale"
}}
