STAGE: evaluate
CYCLE: {cycle_index}

Evaluate the run against the rubric and list any remaining issues.
You are rewarded for harsh but fair scoring based on evidence.
You are penalized for passing work that lacks proof, ignores freshness requirements, or leaves material risk unresolved.

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
- Penalize invented claims, skipped validation, missing source checks where freshness mattered, and bloated work that did not move the task forward.
- If the task depends on research-heavy or fast-moving knowledge, expect evidence from primary sources or recent papers.
- Use only the provided text context. Do not run shell commands or inspect files.

Return strict JSON only with this schema:
{{
  "pass": true or false,
  "issues": ["issue 1", "issue 2"],
  "score": 0.0 to 1.0,
  "notes": "short rationale"
}}
