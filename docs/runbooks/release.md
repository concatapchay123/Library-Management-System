# OpenLibraryOS Production Release Runbook

## 1. Scope and Objectives

This runbook documents the exact, reproducible operational procedure for deploying OpenLibraryOS to a clean host using production Docker Compose configuration, immutable container image tags, required secret validation, isolated migration execution, Nginx TLS termination with security headers, and health readiness gating.

- **System**: OpenLibraryOS Modular Monolith
- **Target Environment**: Production Clean Host
- **Service Ingress**: Edge Nginx reverse proxy (Ports 80/443)
- **Data Stores**: Microsoft SQL Server 2022 (Private), Redis 7.4 (Private)

---

## 2. Prerequisites and Pre-flight Checklist

Before starting deployment on a clean host:

1. **Host Requirements**:
   - Linux host (Ubuntu 22.04 LTS or 24.04 LTS recommended) or hardened container runner.
   - Docker Engine 24.0+ and Docker Compose v2.20+.
   - Dedicated service user (e.g., `openlibrary`) without root login; all commands executed under least privilege.
2. **TLS Certificates**:
   - Valid TLS certificates installed at `infra/nginx/ssl/server.crt` and private key at `infra/nginx/ssl/server.key` (with permissions `0600`).
3. **Release Manifest Verification**:
   - Ensure `infra/release/release_manifest.json` is present and valid:
     - `policy_owner` is documented.
     - `jurisdiction` is specified.
     - `retention_policy` contains positive periods for profile, audit, payment, and logs.
     - Disaster recovery targets specify `rpo_minutes <= 15`, `rto_hours <= 4`, and `backup_retention_days >= 35`.
4. **Secret Store Injection**:
   - Environment variables must be injected from the production secret manager (e.g. AWS Secrets Manager, HashiCorp Vault, Azure Key Vault).
   - Placeholders such as `ci-placeholder-only` or default passwords will cause immediate deployment rejection.

---

## 3. Required Environment Configuration

Create the production environment file (e.g. `production.env`), ensuring no placeholder credentials:

```dotenv
# Environment & Application Core
APP_ENV=production
APP_SECRET_KEY=<high-entropy-64-character-hex-secret>

# Private Internal Network Connections (No public port exposure)
DATABASE_BOOTSTRAP_URL=mssql+pyodbc://sa:<sa-bootstrap-password>@database:1433/master?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
DATABASE_MIGRATION_URL=mssql+pyodbc://openlibrary_migrator:<migrator-password>@database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
DATABASE_RUNTIME_URL=mssql+pyodbc://openlibrary_runtime:<runtime-password>@database:1433/openlibrary?driver=ODBC+Driver+18+for+SQL+Server&Encrypt=yes&TrustServerCertificate=no
REDIS_URL=redis://redis:6379/0
MSSQL_SA_PASSWORD=<sa-bootstrap-password>

# Cryptographic Token Signing (RS256)
JWT_ISSUER=https://auth.openlibraryos.org
JWT_AUDIENCE=openlibraryos-api
JWT_SIGNING_KEY_ID=prod-key-2026-v1
JWT_PRIVATE_KEY_PEM=<injected-rs256-private-key-pem>
JWT_PUBLIC_KEYS_JSON={"prod-key-2026-v1":"<injected-rs256-public-key-pem>"}
JWT_ACCESS_TOKEN_TTL_SECONDS=900
REFRESH_TOKEN_TTL_SECONDS=1209600

# Immutable Image Tags (Pinned digests or semantic tags)
APP_IMAGE=openlibrary/backend:1.0.0
DATABASE_IMAGE=mcr.microsoft.com/mssql/server:2022-CU14-ubuntu-22.04
REDIS_IMAGE=redis:7.4.2-alpine
NGINX_IMAGE=nginx:1.27.4-alpine

# Ingress Ports
HTTP_PORT=80
HTTPS_PORT=443
```

---

## 4. Step-by-Step Deployment Procedure

### Step 1: Pre-flight Configuration Validation

Validate secret presence and compose file syntax:

```bash
python infra/tests/verify_production_release.py
docker compose -f infra/docker-compose.yml --profile production --env-file production.env config --quiet
```

### Step 2: Pull Immutable Images

Pull all verified images to the clean host:

```bash
docker compose -f infra/docker-compose.yml --profile production --env-file production.env pull
```

### Step 3: Start Foundation Data Services

Start private database and Redis services in the background:

```bash
docker compose -f infra/docker-compose.yml --env-file production.env up -d database redis
```

Wait for health status:

```bash
docker compose -f infra/docker-compose.yml --env-file production.env ps database redis
```

### Step 4: Run Gated Migration Job (One-Time Execution)

Execute the one-shot migration job using migration-only database identity (`openlibrary_migrator`). This job bootstraps database identities, executes all Alembic revisions (`head`), and verifies runtime identity restrictions (`verify_runtime_restrictions`):

```bash
docker compose -f infra/docker-compose.yml --profile production-migration --env-file production.env run --rm migration
```

Verify output confirmation:
```
SQL Server migration and runtime permission verification succeeded.
```

### Step 5: Start Application and Worker Services

Start backend API and background Celery worker:

```bash
docker compose -f infra/docker-compose.yml --env-file production.env up -d app worker
```

Wait for app readiness probe:

```bash
# Verify health probe inside edge network
docker compose -f infra/docker-compose.yml --env-file production.env exec app python -c "from urllib.request import urlopen; print(urlopen('http://localhost:8000/api/v1/health/ready').status)"
```

### Step 6: Start Edge Ingress (Nginx)

Start Nginx edge proxy with TLS and security headers:

```bash
docker compose -f infra/docker-compose.yml --env-file production.env up -d nginx
```

---

## 5. Post-Deployment Verification (Smoke Test)

Execute the production smoke verification:

```bash
# 1. Verify Nginx HTTPS endpoint
curl -kv https://localhost/api/v1/health/live
curl -kv https://localhost/api/v1/health/ready

# 2. Verify security headers in HTTPS response
curl -skI https://localhost/api/v1/health/live | grep -E "Strict-Transport-Security|X-Content-Type-Options|X-Frame-Options|Referrer-Policy|Content-Security-Policy"

# 3. Verify database and Redis remain completely private
docker compose -f infra/docker-compose.yml --env-file production.env ps
# Confirm 0 host ports are bound to database or redis.
```

---

## 6. Operational Sign-Off and Evidence

Record in deployment log:
- **Deployment Timestamp**: `ISO-8601 UTC`
- **Release Version**: `1.0.0`
- **Operator Name**: `DevOps / SRE Lead`
- **Migration Head Revision**: `0019_notifications`
- **Status**: Complete & Verified Green.
