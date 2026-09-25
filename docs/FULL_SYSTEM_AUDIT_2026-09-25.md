# OpenLibraryOS -- Full-System Audit Report

**Date:** 2026-09-25
**Scope:** Read-only audit of the current working tree, committed application at
`a2d652c`, frontend runtime observation, API contract, configuration, quality
gates, and dependency metadata.
**No product source, configuration, secrets, database, or deployment state was changed.**

## Executive summary

The project has a broad feature surface (28 backend tasks and 10 frontend
tasks are marked complete) and its static quality gates are healthy.  It is
**not production-ready**.  There are confirmed failures in browser session
recovery, protected Public Library requests, one API method mismatch, and the
current uncommitted deployment change set.  In addition, the most important
SQL Server/RLS/concurrency tests did not run in this audit because no
integration credentials were supplied.

The highest-priority actions are: rotate/remove the exposed development
private key and credentials before they can be committed, correct the browser
authentication flow, pass the access token to Public Library calls, correct
the membership-plan HTTP method, and restore a finite migration command.

## Method and evidence

### Static and automated checks

| Check | Result | Interpretation |
| --- | --- | --- |
| `cd backend; python -m pytest -q` | `345 passed, 53 skipped` | Unit/API coverage passed; real SQL Server coverage is unverified. |
| `cd backend; python -m ruff format --check .`, `ruff check .`, `mypy src` | Pass | Formatting, lint and static type checks passed. |
| `cd frontend; npm run test` | `132 passed` | Frontend unit/component tests passed. |
| `npm run typecheck`, `npm run lint`, `npm run build` | Pass | TypeScript, ESLint and Vite production build passed. |
| OpenAPI validator and compatibility self-check | Pass | YAML is valid; self-comparison cannot find implementation drift. |
| Compose config with CI env and current `.env.example` | Pass | Syntax/interpolation only; containers were not started. |
| `npm audit` | 2 moderate findings | Affected package is development dependency Vitest. |
| Production release script | `6 passed, 0 failed` | Structural assertions only, not an actual deployment test. |

`pip_audit` was also attempted, but it audited the shared Python environment,
not a locked project environment, and exited non-zero because the local
project itself is not published on PyPI.  Its unrelated host-environment CVEs
are deliberately not reported as OpenLibraryOS findings.

### Browser/runtime observation

The Vite frontend was started at `http://127.0.0.1:5173/` and inspected with
Computer Use in Edge.  No account was used and no form carrying business data
was submitted.  The following routes were visually inspected:

- default Circulation desk;
- Catalog search (an empty search was submitted);
- Inventory;
- Education & Members;
- Reservations;
- Public Library & Finance.

The standalone frontend returned HTTP `404` for API calls because it was run
without the Flask backend/proxy.  This does **not** prove that backend routes
are missing.  It did expose how the real UI behaves when its backend is
unavailable, which is an important reliability and truthfulness check.

## Confirmed findings

### Critical

#### C-01 -- An uncommitted environment template exposes a complete signing key and fixed database credentials

- **Scope:** current uncommitted file only; it is not present in `HEAD`.
- **Evidence:** root `.env.example` contains a complete PEM private key plus
  fixed SA, migration and runtime database credentials.  `.gitignore`
  explicitly permits `.env.example` to be committed.
- **Impact:** if this file is committed, pushed, copied to a non-local host, or
  its values have been used outside a disposable environment, an attacker can
  mint JWTs and use known database credentials.  Treat the material as
  compromised if it ever left the workstation.
- **Required remediation:** remove the private key and real-looking passwords
  from the template; use explicit placeholders/generation instructions; rotate
  every exposed key/password before publication.

#### C-02 -- Refresh-session CSRF cookie is inaccessible to the SPA

- **Evidence:** backend sets `csrf_token` with path `/api/v1/auth`
  ([auth.py](../backend/src/openlibrary/modules/core/api/auth.py)), but frontend
  reads `document.cookie` while the document route is `/`
  ([apiClient.ts](../frontend/src/shared/api/apiClient.ts)).  Direct JSDOM
  verification produced `root_document_cookie=""` and exposed the same cookie
  only after changing the document path to `/api/v1/auth/refresh`.
- **Impact:** the client cannot send the mandatory `X-CSRF-Token` for refresh,
  logout or password change.  Access-token recovery after a page reload fails
  even if the refresh cookie exists.
- **Required remediation:** make the readable CSRF cookie path available to the
  SPA while retaining its narrow security purpose, and add a real-browser
  login/refresh/logout test.

### High

#### H-01 -- Fresh frontend session is incorrectly treated as authenticated

- **Evidence:** `App` defaults `initialAuthenticated` to `true`, supplies the
  literal token `in-memory-operate-session`, and defaults
  `autoRefreshOnMount` to `false` ([App.tsx](../frontend/src/app/App.tsx)).
  Computer Use showed the unauthenticated local app opening directly at
  **Librarian Desk / Circulation**, not the login view.
- **Impact:** users see a protected operating interface with a token that the
  backend rejects.  It disguises authentication failure as an operational UI.
- **Required remediation:** default to unauthenticated and restore only via a
  successful refresh; bind route visibility to that outcome.

#### H-02 -- Public Library workspace does not send the access token

- **Evidence:** `PublicLibraryWorkspace` calls all six protected list methods
  without `RequestOptions.token`; Fines, Invoices and Payments mutations also
  omit it.  Backend public-library handlers require a verified principal.
- **Impact:** on a real backend these requests return 401 and FE-010 cannot
  load or complete authorized finance actions.
- **Required remediation:** obtain the session token from auth context and pass
  it consistently to every query and mutation; add an integration test that
  asserts the Authorization header.

#### H-03 -- Current deployment migration command never completes

- **Scope:** current uncommitted `infra/docker-compose.yml` change.
- **Evidence:** the `migration` command executes
  `python scripts/run_migrations.py && ... && tail -f /dev/null`.  The release
  runbook calls it as a one-shot `docker compose ... run --rm migration`.
- **Impact:** the documented production migration step hangs after success and
  cannot supply its expected completion signal.
- **Required remediation:** keep one-shot migration execution finite, or use a
  separate health-gated service and update the runbook/service target together.

#### H-04 -- Local secrets are included in Docker build context

- **Scope:** current uncommitted root `.dockerignore` change.
- **Evidence:** `.dockerignore` excludes neither `.env` nor `.env.*`, while
  `infra/Dockerfile.nginx` builds from repository-root context.
- **Impact:** ignored local secrets can be transmitted to Docker/BuildKit even
  if they are not copied into the final image.
- **Required remediation:** exclude environment files, credentials, keys and
  other local-only material at the root build-context boundary.

#### H-05 -- Core database guarantees were not rerun on SQL Server

- **Evidence:** all 53 skipped tests name missing `DATABASE_BOOTSTRAP_URL`,
  `DATABASE_MIGRATION_URL`, and `DATABASE_RUNTIME_URL`.  They include RLS,
  tenant context, database roles, migration behavior, checkout concurrency,
  reservation allocation, audit/outbox, email delivery, payment and worker
  paths.
- **Impact:** passing mock/unit tests cannot prove tenant isolation,
  least-privilege identities, locking or migration reversibility in the
  production database engine.
- **Required remediation:** run every skipped suite against a disposable SQL
  Server instance with all three identities; record no-skip evidence.

### Medium

#### M-01 -- Membership-plan update uses the wrong HTTP method

- **Evidence:** frontend uses `PATCH` for
  `/public-library/membership-plans/{plan_id}`, while both backend and OpenAPI
  define only `PUT`.
- **Impact:** the typed client method returns HTTP 405 whenever it is used.
- **Required remediation:** make client, contract and server use one method and
  regression-test it.

#### M-02 -- API compatibility gate misses implementation drift

- **Evidence:** backend registers an additional `/public-library/plans` alias,
  but OpenAPI and frontend document only `/membership-plans`.  The current
  compatibility command compares `v1.yaml` to itself, so it cannot detect
  running-route versus contract discrepancies.
- **Impact:** undocumented surface area accumulates and clients can silently
  diverge from server behavior.
- **Required remediation:** remove the alias or document it deliberately; add
  a route-to-OpenAPI parity test.

#### M-03 -- Browser fallback states give contradictory operational signals

- **Evidence from live UI:**
  - Circulation displays **“SUCCESS - Operational Status: Ready”** before any
    successful server check.
  - Inventory shows a fixed selected title, *Designing Data-Intensive
    Applications*, while its data requests fail.
  - Reservations shows **All Items (0)** alongside a 404 error and claims
    synchronization with authoritative backend state.
  - Public Library shows a 404 error but also zero-count tabs and “No public
    library members found.”
- **Impact:** an outage or misconfigured deployment can be misread as a valid
  empty library or a ready desk, causing unsafe operator decisions.
- **Required remediation:** use explicit unavailable/unknown states, hide
  sample data from runtime UI, and do not render authoritative counts after a
  failed request.

#### M-04 -- Production verification is structural, not operational

- **Evidence:** `verify_production_release.py` validates an in-memory sample
  environment dictionary; it does not load `production.env`, start Compose,
  apply migrations, or make HTTPS requests.  It passed 6/6 despite the
  incomplete runtime evidence above.
- **Impact:** the release gate can provide false confidence about secret
  quality, real service ordering, TLS, migration completion and smoke paths.
- **Required remediation:** retain structural checks, then add an isolated
  clean-host Compose test using injected disposable secrets and live probes.

#### M-05 -- Backend functionality has no corresponding SPA flow

- **Evidence:** backend exposes password change, organization-settings update,
  catalog writes, reservation claim, invoice editing/refund/allocation paths,
  while the SPA does not expose a complete user flow for them.
- **Impact:** “completed” backend features are inaccessible to normal browser
  operators, or require an undocumented external client.
- **Required remediation:** explicitly classify each API as admin/API-only or
  implement and test its frontend flow.

#### M-06 -- Dependency/reproducibility gaps

- **Evidence:** backend has no lockfile and Docker installs version ranges at
  build time; base images use mutable tags instead of digests.  `npm audit`
  reports the Vitest/@vitest-mocker path-traversal advisory (moderate; fixed in
  Vitest 5.0.2).
- **Impact:** builds are not fully reproducible and CI/test infrastructure has
  a known vulnerable dependency.
- **Required remediation:** introduce a reviewed Python lock/SBOM process,
  pin production images by digest, and plan the Vitest major upgrade with test
  verification.

#### M-07 -- Vietnamese-facing usability is incomplete

- **Evidence from live UI:** all product navigation, controls, validation and
  operational messages are English.  At a narrow browser viewport the six
  navigation items wrap over multiple rows while a separate Menu button is
  also visible, increasing header density.
- **Impact:** this conflicts with the stated low-cognitive-overhead operator
  goal for Vietnamese users and makes compact-device navigation less clear.
- **Required remediation:** establish a Vietnamese/i18n content decision and
  test responsive navigation at supported breakpoints.

## Findings not classified as confirmed defects

- Standalone Vite API requests received 404 because no Flask API/proxy was
  running.  This is expected for that launch mode, not proof that the committed
  backend lacks endpoints.
- The browser visual audit did not log in or execute a business mutation;
  there was no supplied test identity and this avoids altering user data.
- The current Alembic `DefaultImpl` monkey patch and manual version-table DDL
  are uncommitted and have not been validated on SQL Server in this audit.  It
  should be treated as a migration-risk review item, not yet as a proven
  failure.

## Recommended remediation order

1. **Stop publication of the current uncommitted deployment files.** Remove
   secrets, rotate any material that escaped, and fix `.dockerignore`.
2. **Repair authentication end-to-end**: no synthetic initial token; valid
   refresh/CSRF cookie path; browser tests for login, reload, refresh and
   logout.
3. **Repair frontend/server integration**: Public Library authorization,
   membership-plan `PUT`, and route/OpenAPI parity tests.
4. **Make failure UI truthful**: no hard-coded operational/success/sample
   states after failed requests; ensure zero is rendered only from a successful
   response.
5. **Run the complete SQL Server suite without skips** and add a real Compose
   deployment/release test.
6. **Close operational gaps**: finite migration job, actual production secret
   validation, lockfiles/digests, and an intentional API-to-UI coverage matrix.

## Audit limitations

This is a detailed evidence-based audit, not a penetration test.  No external
network scanning, real credentials, payment provider, email provider, or
production infrastructure was used.  Delegated OCR was attempted but could
not run because its LLM endpoint is not configured on this workstation.
