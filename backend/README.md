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

`APP_SECRET_KEY`, `DATABASE_MIGRATION_URL`, `DATABASE_RUNTIME_URL`, and
`REDIS_URL` are required before the app or worker is created.
`MSSQL_SA_PASSWORD` initializes local SQL Server only; migration and runtime
credentials remain separate URLs. SQL Server and Redis have no host port;
the local API is proxied by Nginx at `http://localhost:8080`.

## Lệnh kiểm tra chuẩn

Chạy từ thư mục `backend`:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy src
```
