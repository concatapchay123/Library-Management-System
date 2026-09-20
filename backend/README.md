# Backend package

Backend Phase 1 bắt đầu với Flask app factory và health endpoints theo [kiến trúc](../docs/architecture.md). SQLAlchemy integration, migrations và business modules được bổ sung ở các task backend kế tiếp.

## Thiết lập

```powershell
python -m pip install -e ".[dev]"
```

## Local runtime

`backend/.env.example` lists names only. Copy it to an ignored environment
file, supply deployment values, then validate Compose from the repository root:

```powershell
docker compose --env-file backend/.env -f infra/docker-compose.yml config
```

`APP_SECRET_KEY`, `DATABASE_RUNTIME_URL`, and `REDIS_URL` are required before
the app or worker is created. The app and worker never receive migration
credentials. SQL Server and Redis have no host port; the local API is proxied
by Nginx at `http://localhost:8080`.

## SQL Server migration bootstrap

The deployment job, not an app or worker replica, supplies three distinct
database URLs in its environment: `DATABASE_BOOTSTRAP_URL` for initial
server/database principal provisioning, `DATABASE_MIGRATION_URL` for Alembic,
and `DATABASE_RUNTIME_URL` for the least-privilege application identity.
Provision an empty target database, then run this command from `backend`:

```powershell
python scripts/run_migrations.py
```

The command creates the configured migration and runtime principals when they
do not exist, applies Alembic revisions with the migration identity, and fails
if the runtime identity has `db_owner`, `CONTROL`, `IMPERSONATE`, or
`ALTER ANY SECURITY POLICY`. The URLs and `MSSQL_SA_PASSWORD` remain
deployment secrets and are never committed.

## Lệnh kiểm tra chuẩn

Chạy từ thư mục `backend`:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy src
```
