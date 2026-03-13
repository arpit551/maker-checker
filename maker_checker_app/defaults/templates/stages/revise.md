STAGE: revise
CYCLE: {cycle_index}

Revise the plan using the critique and recent run memory.

## Task Brief
{task_prompt}

## Evaluation Brief
{evaluation_prompt}

## Recent Run Memory
{recent_run_memory}

## Discovery Findings
{discover_output}

## Current Plan
{plan_output}

## Claude Critique
{critique_output}

## Revision Rules
- Use only the provided text context.
- Fix every valid critique item explicitly.
- Ignore critique points that rely on guessed repository facts or guessed environment state.
- Add research or inspection steps only where they materially change correctness, risk, or implementation choices.
- Remove duplicated or low-leverage steps so the plan stays lean.
- Do not inspect or modify repository state while revising.
- Replace user-directed follow-up questions with direct checks, safe defaults, or explicit blocker branches whenever possible.
- Preserve any explicit verification command, budget, or artifact requirement from the evaluation brief unless the critique gives a grounded reason to change it.
- If the critique contains ungrounded claims, drop them rather than carrying them forward.

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Research, Steps, Risks, Success checks.
- In `Research`, write `none` if no extra research is needed.
- Address critique items explicitly.
- Remove invented assumptions rather than doubling down on them.
