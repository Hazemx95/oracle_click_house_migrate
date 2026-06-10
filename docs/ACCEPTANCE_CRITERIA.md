# Acceptance Criteria

## Global Acceptance Gates

Every phase must satisfy these gates before it is considered complete:

- Oracle remains read-only.
- ClickHouse writes target only `oracle_migration_hazem`.
- Credentials are environment-based only.
- Real `.env` files are not committed.
- No credentials appear in logs, responses, docs, tests, or committed config.
- Schema, table, and column names are validated before use.
- Large-table data movement uses bounded batches, not full-table memory loads.
- The current phase's manual test commands are documented and run.
- The current phase's stop point is respected.

## Phase 0 Acceptance Criteria

Phase 0 is complete only when:

- `docs/PROJECT_RULES.md` exists and documents phase discipline and project rules.
- `docs/SECURITY_RULES.md` exists and documents Oracle read-only and ClickHouse target restrictions.
- `docs/PHASE_EXECUTION_GUIDE.md` exists and requires acceptance criteria and manual test commands for future phases.
- `docs/ENVIRONMENT_RULES.md` exists and documents environment-only credentials and real `.env` exclusion.
- `docs/ACCEPTANCE_CRITERIA.md` exists and defines global gates.
- `.specify/memory/constitution.md` exists and states the seven binding principles.
- `.gitignore` ignores real environment files.
- `.dockerignore` excludes real environment files from Docker build context.

## Phase 0 Manual Tests

```bash
test -f docs/PROJECT_RULES.md
test -f docs/SECURITY_RULES.md
test -f docs/PHASE_EXECUTION_GUIDE.md
test -f docs/ENVIRONMENT_RULES.md
test -f docs/ACCEPTANCE_CRITERIA.md
test -f .specify/memory/constitution.md
git check-ignore .env
git check-ignore .env.local
git check-ignore production.env
```

## Future Phase Rule

Every future phase MUST include acceptance criteria and manual test commands
before coding starts. A future phase without both is not ready for implementation.
