# Security Rules

## Oracle Source Safety

Oracle is read-only. The application MUST NOT modify Oracle in any phase.

Allowed Oracle operation:

```sql
SELECT
```

Forbidden Oracle operations:

```sql
CREATE
ALTER
DROP
TRUNCATE
INSERT
UPDATE
DELETE
MERGE
EXEC
CALL
```

The application MUST NOT change any Oracle source schema, table, data, trigger,
procedure, or job.

## ClickHouse Target Safety

All ClickHouse writes MUST be confined to this database:

```text
oracle_migration_hazem
```

Allowed ClickHouse operations inside `oracle_migration_hazem` only:

```sql
CREATE TABLE IF NOT EXISTS
INSERT INTO
SELECT
```

The application MUST reject any create, insert, or migration operation targeting
another ClickHouse database.

Optional rerun operations such as `TRUNCATE TABLE` and `DROP TABLE` MUST NOT be
implemented unless explicitly required in a later phase, and if implemented they
must still be restricted to `oracle_migration_hazem`.

## Input Safety

- Oracle schema and table values MUST be validated against Oracle metadata.
- Oracle parameter values MUST use bind variables.
- Raw user input MUST NOT be concatenated into SQL.
- Dangerous target database values MUST be rejected before execution.

## Secret Safety

- Credentials MUST NOT appear in source code, Dockerfile, Docker Compose, README, PLAN.md, docs, tests, logs, or API responses.
- Errors must be clear but credential-free.
- Real `.env` files and local secret files must stay ignored by Git and Docker context.
