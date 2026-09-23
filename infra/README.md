# Infrastructure package

## Local SQL Server migration and test jobs

Copy `backend/.env.example` to the ignored `backend/.env` and provide
`MSSQL_SA_PASSWORD` plus the three SQL-auth URLs. Docker service names are
used as hosts, and passwords in the URLs must be percent-encoded when they
contain URL-reserved characters.

```dotenv
DATABASE_BOOTSTRAP_URL=mssql+pyodbc://sa:<encoded-sa-password>@database:1433/master?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes
DATABASE_MIGRATION_URL=mssql+pyodbc://openlibrary_migrator:<encoded-migration-password>@database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes
DATABASE_RUNTIME_URL=mssql+pyodbc://openlibrary_runtime:<encoded-runtime-password>@database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=yes
JWT_ISSUER=https://identity.example.invalid
JWT_AUDIENCE=openlibraryos-api
JWT_SIGNING_KEY_ID=<active-rs256-key-id>
JWT_PRIVATE_KEY_PEM=<secret-manager-injected-rs256-private-pem>
JWT_PUBLIC_KEYS_JSON={"<active-rs256-key-id>":"<active-rs256-public-pem>"}
JWT_ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=1209600
```

When rotating an access-token signing key, deploy the new private key and
retain every previous public key in `JWT_PUBLIC_KEYS_JSON` until its last
possible issued token has exceeded `JWT_ACCESS_TOKEN_TTL_SECONDS`.

The `migration` profile runs a one-shot `database-init` service that creates
the local `openlibrary` database if needed, then executes the existing
identity bootstrap and Alembic migration command. App and worker containers
never receive bootstrap or migration URLs.

```powershell
docker compose --env-file backend/.env -f infra/docker-compose.yml --profile migration run --rm migration
docker compose --env-file backend/.env -f infra/docker-compose.yml up --build
```

The `test` profile creates the same local database boundary, runs the
migration workflow, and executes the BE-005 SQL Server integration suite
inside the private Docker network:

```powershell
docker compose --env-file backend/.env -f infra/docker-compose.yml --profile test run --rm tests
```

## Production Compose profile and release verification

Production deployment uses the `production` profile, immutable image tags, separate migration identities, and readiness-gated orchestration. Production configuration is verified via `infra/tests/test_production_release.ps1` and governed by the release manifest at `infra/release/release_manifest.json`.

```powershell
# Run release verification gates
powershell -ExecutionPolicy Bypass -File infra/tests/test_production_release.ps1

# Run disaster recovery and rehearsal checks
python infra/scripts/manage_dr.py

# Deploy production profile on clean host
docker compose --env-file production.env -f infra/docker-compose.yml --profile production-migration run --rm migration
docker compose --env-file production.env -f infra/docker-compose.yml up -d app worker nginx
```

Operational runbooks:
- [Production Release Runbook](../docs/runbooks/release.md)
- [Disaster Recovery & Restore Runbook](../docs/runbooks/restore.md)
- [Rollback & Forward-Fix Runbook](../docs/runbooks/rollback.md)
