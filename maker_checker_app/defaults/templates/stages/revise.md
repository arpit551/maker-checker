STAGE: revise
CYCLE: {cycle_index}

Revise the plan using the critique and recent run memory.
You are rewarded for fixing critique items cleanly and trimming unnecessary work.
You are penalized for defending weak assumptions, bloating the plan, or preserving stale research paths.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Current Plan
{plan_output}

## Claude Critique
{critique_output}

## Revision Rules
- Fix every valid critique item explicitly.
- Add research steps only where they materially change correctness, risk, or implementation choices.
- When freshness matters and your environment supports it, route bounded research or validation work to sub-agents.
- Prefer primary sources, official docs, standards, and recent papers for research-heavy claims.
- Remove duplicated or low-leverage steps so the plan stays lean.
- Do not inspect or modify repository state while revising.

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Research, Steps, Risks, Success checks.
- In `Research`, write `none` if no extra research is needed.
- Address critique items explicitly.
- Remove invented assumptions rather than doubling down on them.
