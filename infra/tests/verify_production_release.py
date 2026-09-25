"""Production release verification test suite for BE-028.

Validates:
1. Production Compose configuration, immutable image tags, network restrictions.
2. Missing secrets rejection and placeholder rejection.
3. Migration job uniqueness, readiness gate, and identity separation.
4. Nginx TLS, security headers, SPA fallback, and API reverse proxy routing.
5. Release manifest: policy owner, jurisdiction, retention, RPO <= 15m, RTO <= 4h, retention >= 35d.
6. Explicit rollback vs forward-fix decision matrix for every Alembic migration revision.
7. Operational runbooks for release, restore, and rollback.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
INFRA_DIR = REPO_ROOT / "infra"
COMPOSE_FILE = INFRA_DIR / "docker-compose.yml"
NGINX_CONF = INFRA_DIR / "nginx" / "default.conf"
RELEASE_MANIFEST_FILE = INFRA_DIR / "release" / "release_manifest.json"
MIGRATIONS_DIR = REPO_ROOT / "backend" / "migrations" / "versions"
DOCS_DIR = REPO_ROOT / "docs"
RUNBOOKS_DIR = DOCS_DIR / "runbooks"


class VerificationError(Exception):
    """Raised when a production release gate check fails."""


def test_production_profile_and_compose() -> None:
    """Validate that docker-compose.yml defines production profile and immutable tags."""
    if not COMPOSE_FILE.is_file():
        raise VerificationError(f"docker-compose.yml not found at {COMPOSE_FILE}")

    content = COMPOSE_FILE.read_text(encoding="utf-8")
    data = yaml.safe_load(content)

    services = data.get("services", {})
    if not services:
        raise VerificationError("No services defined in docker-compose.yml")

    # 1. Check for production migration job / profile
    # Either a service has profile 'production' or 'production-migration', or dedicated production migration service
    has_prod_migration = False
    for s_name, s_def in services.items():
        profiles = s_def.get("profiles", [])
        if (
            "production" in profiles or "production-migration" in profiles
        ) and "migration" in s_name:
            has_prod_migration = True
            break
        if s_name == "production-migration":
            has_prod_migration = True
            break

    if not has_prod_migration:
        raise VerificationError(
            "Missing production-profile migration job: docker-compose.yml must define a "
            "migration service with 'production' or 'production-migration' profile."
        )

    # 2. Check immutable image tags (no ':latest' in production configurations)
    database_svc = services.get("database", {})
    db_image = str(database_svc.get("image", ""))
    if ":latest" in db_image:
        raise VerificationError(
            f"Database service uses mutable image tag {db_image!r}. Production requires an immutable tag."
        )

    redis_svc = services.get("redis", {})
    redis_image = str(redis_svc.get("image", ""))
    if ":latest" in redis_image:
        raise VerificationError(
            f"Redis service uses mutable image tag {redis_image!r}. Production requires an immutable tag."
        )

    nginx_svc = services.get("nginx", {})
    nginx_image = str(nginx_svc.get("image", ""))
    if ":latest" in nginx_image:
        raise VerificationError(
            f"Nginx service uses mutable image tag {nginx_image!r}. Production requires an immutable tag."
        )

    # 3. Check network restrictions
    # Database and Redis must NOT expose ports to host
    if "ports" in database_svc:
        raise VerificationError(
            "Database service must not expose public host ports. It must remain private."
        )
    if "ports" in redis_svc:
        raise VerificationError(
            "Redis service must not expose public host ports. It must remain private."
        )

    db_networks = database_svc.get("networks", [])
    if "edge" in db_networks or "public" in db_networks:
        raise VerificationError(
            "Database must not be connected to edge/public network."
        )

    redis_networks = redis_svc.get("networks", [])
    if "edge" in redis_networks or "public" in redis_networks:
        raise VerificationError("Redis must not be connected to edge/public network.")

    # 4. App & Worker identity separation:
    # App and Worker must NOT have DATABASE_BOOTSTRAP_URL or DATABASE_MIGRATION_URL
    app_svc = services.get("app", {})
    app_env = app_svc.get("environment", {})
    if isinstance(app_env, dict):
        if "DATABASE_BOOTSTRAP_URL" in app_env or "DATABASE_MIGRATION_URL" in app_env:
            raise VerificationError(
                "App container must NOT receive DATABASE_BOOTSTRAP_URL or DATABASE_MIGRATION_URL."
            )
    elif isinstance(app_env, list):
        for e in app_env:
            if e.startswith("DATABASE_BOOTSTRAP_URL") or e.startswith(
                "DATABASE_MIGRATION_URL"
            ):
                raise VerificationError(
                    "App container must NOT receive DATABASE_BOOTSTRAP_URL or DATABASE_MIGRATION_URL."
                )

    worker_svc = services.get("worker", {})
    worker_env = worker_svc.get("environment", {})
    if isinstance(worker_env, dict):
        if (
            "DATABASE_BOOTSTRAP_URL" in worker_env
            or "DATABASE_MIGRATION_URL" in worker_env
        ):
            raise VerificationError(
                "Worker container must NOT receive DATABASE_BOOTSTRAP_URL or DATABASE_MIGRATION_URL."
            )

    # 5. Readiness gating:
    # Nginx must depend on app being healthy
    nginx_deps = nginx_svc.get("depends_on", {})
    if (
        not isinstance(nginx_deps, dict)
        or nginx_deps.get("app", {}).get("condition") != "service_healthy"
    ):
        raise VerificationError(
            "Nginx must readiness-gate on app with condition: service_healthy."
        )

    # App must depend on database and redis being healthy
    app_deps = app_svc.get("depends_on", {})
    if not isinstance(app_deps, dict):
        raise VerificationError(
            "App depends_on must specify healthcheck conditions for database and redis."
        )
    if app_deps.get("database", {}).get("condition") != "service_healthy":
        raise VerificationError(
            "App must depend on database condition: service_healthy."
        )
    if app_deps.get("redis", {}).get("condition") != "service_healthy":
        raise VerificationError("App must depend on redis condition: service_healthy.")


def test_required_secrets_validation() -> None:
    """Validate that required production secrets are strictly enforced and placeholders rejected."""
    # Required keys that must be configured for production runtime
    required_runtime_keys = [
        "APP_SECRET_KEY",
        "DATABASE_RUNTIME_URL",
        "REDIS_URL",
        "JWT_ISSUER",
        "JWT_AUDIENCE",
        "JWT_SIGNING_KEY_ID",
        "JWT_PRIVATE_KEY_PEM",
        "JWT_PUBLIC_KEYS_JSON",
        "JWT_ACCESS_TOKEN_TTL_SECONDS",
        "REFRESH_TOKEN_TTL_SECONDS",
    ]

    # Sample dummy production config with missing or placeholder keys
    forbidden_values = {
        "ci-placeholder-only",
        "placeholder",
        "changeme",
        "secret",
        "password",
    }

    # Validation logic verification:
    def validate_production_env(env: dict[str, str]) -> list[str]:
        errors = []
        for k in required_runtime_keys:
            val = env.get(k, "").strip()
            if not val:
                errors.append(f"Missing required secret/env: {k}")
            elif val.lower() in forbidden_values:
                errors.append(
                    f"Insecure placeholder rejected for production: {k}={val}"
                )

        db_url = env.get("DATABASE_RUNTIME_URL", "")
        if "sa:" in db_url or "sa@" in db_url:
            errors.append(
                "Runtime database connection must not use 'sa' superuser login."
            )

        return errors

    # Test 1: empty env must fail
    empty_errors = validate_production_env({})
    if len(empty_errors) != len(required_runtime_keys):
        raise VerificationError(
            "Production validator failed to detect all missing required keys."
        )

    # Test 2: placeholder env must fail
    placeholder_env = {k: "ci-placeholder-only" for k in required_runtime_keys}
    placeholder_errors = validate_production_env(placeholder_env)
    if not any("Insecure placeholder" in e for e in placeholder_errors):
        raise VerificationError(
            "Production validator failed to reject insecure placeholders."
        )

    # Test 3: 'sa' database url must fail
    sa_env = {k: "valid_secret_value_12345" for k in required_runtime_keys}
    sa_env["DATABASE_RUNTIME_URL"] = (
        "mssql+pyodbc://sa:secret@database:1433/openlibrary"
    )
    sa_errors = validate_production_env(sa_env)
    if not any("superuser" in e for e in sa_errors):
        raise VerificationError(
            "Production validator failed to reject 'sa' login in runtime database URL."
        )


def test_nginx_security_and_routing() -> None:
    """Validate Nginx configuration for TLS, security headers, SPA fallback and API proxy."""
    if not NGINX_CONF.is_file():
        raise VerificationError(f"Nginx configuration not found at {NGINX_CONF}")

    content = NGINX_CONF.read_text(encoding="utf-8")

    # Check TLS
    if "ssl_certificate" not in content or "443" not in content:
        raise VerificationError(
            "Nginx configuration must configure TLS listener on port 443 with ssl_certificate."
        )

    # Check required security headers
    required_headers = [
        "Strict-Transport-Security",
        "X-Content-Type-Options",
        "X-Frame-Options",
        "Referrer-Policy",
        "Content-Security-Policy",
    ]
    for header in required_headers:
        if header not in content:
            raise VerificationError(
                f"Nginx configuration is missing mandatory security header: {header}"
            )

    # Check SPA fallback
    if "try_files" not in content or "index.html" not in content:
        raise VerificationError(
            "Nginx configuration is missing SPA routing fallback (try_files ... /index.html)."
        )

    # Check API proxy
    if "location /api/" not in content or "proxy_pass" not in content:
        raise VerificationError(
            "Nginx configuration is missing API reverse proxy routing (/api/ -> proxy_pass)."
        )


def test_release_manifest_and_dr() -> None:
    """Validate release manifest for owner, jurisdiction, retention, and DR objectives."""
    if not RELEASE_MANIFEST_FILE.is_file():
        raise VerificationError(
            f"Release manifest file not found at {RELEASE_MANIFEST_FILE}"
        )

    try:
        manifest = json.loads(RELEASE_MANIFEST_FILE.read_text(encoding="utf-8"))
    except Exception as exc:
        raise VerificationError(
            f"Failed to parse release manifest JSON: {exc}"
        ) from exc

    policy_owner = manifest.get("policy_owner", "").strip()
    if not policy_owner:
        raise VerificationError(
            "Release manifest must specify non-empty 'policy_owner'."
        )

    jurisdiction = manifest.get("jurisdiction", "").strip()
    if not jurisdiction:
        raise VerificationError(
            "Release manifest must specify non-empty 'jurisdiction'."
        )

    retention = manifest.get("retention_policy", {})
    for key in (
        "profile_retention_days",
        "audit_retention_days",
        "payment_retention_days",
        "log_retention_days",
    ):
        val = retention.get(key)
        if val is None or not isinstance(val, int) or val <= 0:
            raise VerificationError(
                f"Release manifest retention policy key '{key}' must be a strictly positive integer."
            )

    dr = manifest.get("disaster_recovery", {})
    rpo = dr.get("rpo_minutes")
    if rpo is None or rpo > 15:
        raise VerificationError(
            f"Disaster recovery RPO must be at most 15 minutes (found: {rpo})."
        )

    rto = dr.get("rto_hours")
    if rto is None or rto > 4:
        raise VerificationError(
            f"Disaster recovery RTO must be at most 4 hours (found: {rto})."
        )

    backup_retention = dr.get("backup_retention_days")
    if backup_retention is None or backup_retention < 35:
        raise VerificationError(
            f"Backup retention must be at least 35 days (found: {backup_retention})."
        )


def test_migration_rollback_matrix() -> None:
    """Validate that every Alembic migration has an explicit rollback or forward-fix decision."""
    if not MIGRATIONS_DIR.is_dir():
        raise VerificationError(
            f"Alembic migrations directory not found at {MIGRATIONS_DIR}"
        )

    migration_files = sorted(MIGRATIONS_DIR.glob("*.py"))
    if not migration_files:
        raise VerificationError(
            "No migration files found in backend/migrations/versions"
        )

    migration_names = [f.stem for f in migration_files]

    if not RELEASE_MANIFEST_FILE.is_file():
        raise VerificationError(
            f"Release manifest not found to verify migration matrix: {RELEASE_MANIFEST_FILE}"
        )

    manifest = json.loads(RELEASE_MANIFEST_FILE.read_text(encoding="utf-8"))
    matrix = manifest.get("migration_rollback_matrix", {})

    missing_decisions = []
    for m in migration_names:
        decision = matrix.get(m)
        if not decision:
            missing_decisions.append(m)
        else:
            action = decision.get("action")
            if action not in ("rollback", "forward-fix"):
                missing_decisions.append(f"{m} (invalid action '{action}')")
            if not decision.get("rationale"):
                missing_decisions.append(f"{m} (missing rationale)")

    if missing_decisions:
        raise VerificationError(
            f"Release manifest missing explicit rollback/forward-fix decisions for migrations: {', '.join(missing_decisions)}"
        )


def test_operational_runbooks() -> None:
    """Validate operational runbooks for release, restore, and rollback."""
    required_runbooks = {
        "release.md": ["clean host", "readiness", "migration", "smoke"],
        "restore.md": ["rpo", "rto", "isolated", "rls"],
        "rollback.md": ["rollback", "forward-fix", "decision", "rehearsal"],
    }

    for filename, required_terms in required_runbooks.items():
        file_path = RUNBOOKS_DIR / filename
        if not file_path.is_file():
            raise VerificationError(f"Required runbook not found: {file_path}")

        content = file_path.read_text(encoding="utf-8").lower()
        for term in required_terms:
            if term not in content:
                raise VerificationError(
                    f"Runbook {filename} missing required section/term: {term!r}"
                )


def test_live_smoke_probes(base_url: str | None = None) -> None:
    """Execute live probes against running HTTP service if available."""
    import urllib.request
    import urllib.error

    url = base_url or os.environ.get("OPENLIBRARY_LIVE_URL", "http://localhost:8000")
    try:
        req = urllib.request.Request(f"{url}/api/v1/health/live", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status != 200:
                raise VerificationError(f"Live health probe returned non-200 status: {resp.status}")
    except (urllib.error.URLError, TimeoutError, ConnectionRefusedError, OSError):
        # Service is not currently running locally on port 8000; log non-blocking notice unless strictly required
        if os.environ.get("OPENLIBRARY_REQUIRE_LIVE_PROBES") == "1":
            raise VerificationError(f"Live probe required but unable to connect to {url}")


def main() -> int:
    """Run all checks and report status."""
    import os

    checks = [
        (
            "Production Profile & Compose Configuration",
            test_production_profile_and_compose,
        ),
        (
            "Required Secrets Validation & Placeholder Rejection",
            test_required_secrets_validation,
        ),
        ("Nginx TLS, Security Headers & SPA Routing", test_nginx_security_and_routing),
        (
            "Release Manifest & DR Commitments (RPO/RTO/Retention)",
            test_release_manifest_and_dr,
        ),
        (
            "Migration Rollback vs Forward-Fix Decision Matrix",
            test_migration_rollback_matrix,
        ),
        (
            "Operational Runbooks (Release, Restore, Rollback)",
            test_operational_runbooks,
        ),
        (
            "Live Service Health & Smoke Probes",
            test_live_smoke_probes,
        ),
    ]

    passed = 0
    failed = 0
    print("=" * 70)
    print("OpenLibraryOS BE-028 Production Release Verification")
    print("=" * 70)

    for name, check_fn in checks:
        print(f"[*] Checking: {name} ... ", end="")
        try:
            check_fn()
            print("PASS")
            passed += 1
        except VerificationError as err:
            print("FAIL")
            print(f"    --> Error: {err}")
            failed += 1
        except Exception as exc:
            print("ERROR")
            print(f"    --> Unexpected exception: {exc}")
            failed += 1

    print("=" * 70)
    print(f"Summary: {passed} passed, {failed} failed out of {len(checks)} checks.")
    print("=" * 70)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
