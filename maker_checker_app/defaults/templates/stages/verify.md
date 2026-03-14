STAGE: verify
CYCLE: {cycle_index}

Run the required validation and list unresolved issues.

## Evaluation Brief
{evaluation_prompt}

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Discovery Findings
{discover_output}

## Revised Plan
{revise_output}

## Execution Report
{execute_output}

## Verification Rules
- Follow plan steps labeled `Verify:` plus any exact validation requirement from the evaluation brief.
- Inspect the repository, changed files, and runtime artifacts as needed.
- Run the exact validation command or bounded runtime check requested by the evaluation brief when one is provided, unless a blocker makes that impossible.
- If the evaluation brief does not provide a command, run the smallest concrete checks that can verify the requested outcome.
- Treat execute-stage smoke checks as supporting evidence only; do not count them as final validation unless they already match the evaluation brief exactly.
- Treat missing evidence, skipped validation, stale-source claims, and "should work" language as issues.
- If the plan depended on research or external facts, confirm the execution report named concrete sources or explain why none were needed.
- Do not assume success from confident language alone.
- If validation is blocked or incomplete, fail verification and describe the blocker directly.

Return strict JSON only with this schema:
{{
  "pass": true or false,
  "issues": ["issue 1", "issue 2"],
  "commands": ["command 1", "command 2"],
  "evidence": ["fact 1", "fact 2"],
  "notes": "short rationale"
}}
