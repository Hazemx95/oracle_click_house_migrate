# Environment Rules

## Configuration Source

All runtime configuration and credentials MUST come from environment variables.
The application MUST NOT hardcode credentials or environment-specific secrets in
committed files.

## Required Environment Variables For Later Phases

```env
CLICKHOUSE_HOST=
CLICKHOUSE_PORT=8123
CLICKHOUSE_USER=
CLICKHOUSE_PASS=
CLICKHOUSE_DATABASE=oracle_migration_hazem
CLICKHOUSE_ALLOW_CREATE_DATABASE=false

P5_QA_ORACLE_USER=
P5_QA_ORACLE_PASSWORD=
P5_QA_ORACLE_HOST=
P5_QA_ORACLE_PORT=1521
P5_QA_ORACLE_SERVICE_NAME=
P5_QA_ORACLE_DSN=

APP_HOST=0.0.0.0
APP_PORT=8000
MIGRATION_BATCH_SIZE=100000
MIGRATION_DEFAULT_WORKERS=8
```

## `.env` Policy

- A real `.env` file is local-only and MUST NOT be committed.
- `.env.example` may be committed with placeholder values only.
- Real passwords, tokens, database hosts, and user-specific values must not appear in committed docs or source files.
- `.gitignore` MUST ignore `.env`, `.env.*`, and `*.env` while allowing `.env.example`.
- `.dockerignore` MUST exclude real `.env` files from the Docker build context.

## Verification Commands

```bash
git check-ignore .env
git check-ignore .env.local
git check-ignore production.env
```

Each command must confirm that the real environment file pattern is ignored.
