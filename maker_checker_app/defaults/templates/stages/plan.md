STAGE: plan
CYCLE: {cycle_index}

Produce the next implementation plan.

## Task Brief
{task_prompt}

## Evaluation Brief
{evaluation_prompt}

## Recent Run Memory
{recent_run_memory}

## Discovery Findings
{discover_output}

## Unresolved Issues From The Previous Cycle
{unresolved_issues_bulleted}

## Previous Plan
{previous_plan}

## Planning Rules
- Use only the provided text context.
- Do not invent repository facts, files, commits, logs, prior runs, test coverage, or environment state that were not provided.
- Start from the task brief, discovery findings, recent run memory, unresolved issues, and previous plan.
- If the evaluation brief specifies an exact verification command, budget, or artifact requirement, reserve that work for the `verify` stage by default. Only put it in `execute` when a smaller reproduction cannot diagnose or de-risk the implementation.
- If later steps depend on credentials, devices, local services, or external tooling, make the first step a preflight check and include an explicit blocker branch instead of assuming success.
- If the next step depends on inspecting the repository, logs, runtime artifacts, or current docs, say exactly what should be checked during execution. Do not pretend that work already happened.
- Do not tell the executor to ask the user for routine runtime details mid-run. Prefer a direct check, a safe default, or an explicit blocker branch.
- Prefer the smallest maintainable path that can be verified clearly.
- Keep the plan concise and concrete. Do not restate the full brief.
- Call out unknowns and evidence needed instead of guessing.
- If the provided context is insufficient, say so explicitly and make the first steps reduce that uncertainty.

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Research, Steps, Risks, Success checks.
- In `Research`, write `none` if no extra research is needed.
- Make the steps specific and ordered.
- In `Steps`, prefix each item with either `Execute:` or `Verify:` so implementation work and final validation are separated clearly.
- Keep `Execute:` steps limited to preflight checks, focused reproduction, code changes, and short smoke checks.
- Put the exact evaluation command and any full-budget rerun in `Verify:` steps unless a broader run is strictly required before code changes.
- Make the steps concrete enough that an executor or sub-agent could pick them up without guessing.
- If the task brief is ambiguous, make the first steps reduce ambiguity instead of inventing requirements.
