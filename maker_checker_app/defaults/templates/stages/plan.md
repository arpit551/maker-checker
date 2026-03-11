STAGE: plan
CYCLE: {cycle_index}

Produce the next implementation plan.
You are rewarded for precise, evidence-backed steps and for keeping context lean.
You are penalized for invented repo facts, stale assumptions, vague plans, or repeating large chunks of the brief.

## Task Brief
{task_prompt}

## Recent Run Memory
{recent_run_memory}

## Unresolved Issues From The Previous Cycle
{unresolved_issues_bulleted}

## Previous Plan
{previous_plan}

## Planning Rules
- Start from the task brief, recent run memory, and unresolved issues.
- If success depends on current APIs, changing docs, security guidance, benchmarks, or research claims, schedule explicit research before implementation.
- If your environment supports it, use parallel sub-agents for bounded research tracks such as docs, tests, recent papers, or API validation.
- Prefer primary sources and official docs; for research-heavy work, prefer recent papers over blog summaries.
- Keep only the information that changes the plan. Do not restate the entire brief.
- Do not inspect or modify repository state while planning.
- During planning make sure plan is very rich icludes code snippets mostly

## Output Requirements
- Return Markdown only.
- Include sections: Goals, Research, Steps, Risks, Success checks.
- In `Research`, write `none` if no extra research is needed.
- Make the steps specific and ordered.
- Make the steps concrete enough that an executor or sub-agent could pick them up without guessing.
- If the task brief is ambiguous, make the first steps reduce ambiguity instead of inventing requirements.
