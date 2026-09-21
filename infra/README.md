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
```

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

Infrastructure Phase 1 sẽ tạo Docker Compose, Nginx và environment templates cho `app`, `worker`, `database`, `redis` và `nginx`. Production rules nằm trong [deployment guide](../docs/deployment.md).
