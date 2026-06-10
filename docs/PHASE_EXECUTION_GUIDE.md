# Phase Execution Guide

## Required Workflow

Every implementation phase must follow this order:

1. Read `PLAN.md`, `specs/001-oracle-clickhouse-migration/spec.md`, `plan.md`, and `tasks.md`.
2. Confirm the current phase scope and explicit non-scope.
3. Verify all prior phase acceptance criteria are complete.
4. Implement only the current phase.
5. Run the phase manual test commands.
6. Mark completed tasks as `[X]` in `tasks.md`.
7. Stop at the phase stop point.

## Phase Boundary Rules

- Do not implement Phase 1 during Phase 0.
- Do not implement a later phase before the current phase is accepted.
- Do not add application code unless the current phase explicitly allows it.
- Do not add backward-compatibility behavior unless a phase explicitly requires it.

## Required Sections For Every Future Phase

Each future phase must document:

- Goal.
- Scope.
- Files to create or update.
- Explicit non-scope.
- Acceptance criteria.
- Manual test commands.
- Stop point.
- Applicable constitution and security gates.

## Phase 0 Manual Test Commands

```bash
test -f docs/PROJECT_RULES.md
test -f docs/SECURITY_RULES.md
test -f docs/PHASE_EXECUTION_GUIDE.md
test -f docs/ENVIRONMENT_RULES.md
test -f docs/ACCEPTANCE_CRITERIA.md
test -f .specify/memory/constitution.md
git check-ignore .env
```

## Stop Point

Stop after Phase 0 guardrail documents exist and `.env` is ignored. Do not start
Phase 1 until the user confirms the guardrails are acceptable.
