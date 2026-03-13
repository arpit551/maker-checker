STAGE: evaluate
CYCLE: {cycle_index}

Evaluate the run against the rubric and list any remaining issues.

## Evaluation Brief
{evaluation_prompt}

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Revised Plan
{revise_output}

## Execution Report
{execute_output}

## Verification Report
{verify_output}

## Evaluation Rules
- Judge the run against the evaluation brief, task brief, revised plan, execution report, and verification report.
- Fail invented claims, skipped validation, missing evidence, and work that does not address the requested outcome.
- If the task depended on current external facts, expect named sources or an explicit explanation of why no source check was needed.
- Use only the provided text context. Do not run shell commands or inspect files.

Return strict JSON only with this schema:
{{
  "pass": true or false,
  "issues": ["issue 1", "issue 2"],
  "score": 0.0 to 1.0,
  "notes": "short rationale"
}}
