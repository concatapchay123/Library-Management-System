# TASK-010 — React application shell and API client

## Task Information

- ID: TASK-010
- Name: Frontend shell, auth flow and module screens
- Priority: P2

## Objective

Create the React SPA shell and typed API integration for the delivered backend modules without duplicating business rules in the browser.

## Scope

Implement app routing, auth refresh flow, organization-scoped UI, typed OpenAPI client, error handling and critical catalog/circulation/edition screens. UI should be functional and accessible; visual redesign is outside this task.

## Files affected

- Create/modify: `frontend/src/app/`, `frontend/src/features/`, `frontend/src/shared/`
- Create: `frontend/tests/`
- Modify: `contracts/openapi/v1.yaml`
- Modify: `infra/nginx/` for SPA fallback and API proxy

## Implementation steps

1. Write failing tests for protected route redirect and refresh failure behavior.
2. Run tests and confirm missing auth state implementation fails.
3. Implement auth provider using HttpOnly refresh cookie and in-memory access token.
4. Generate or implement typed API client from OpenAPI.
5. Add catalog, copy, loan, reservation and notification screens.
6. Add problem-details rendering, loading/empty/error states and keyboard-accessible controls.
7. Run frontend unit, type-check, lint and production build.

## Dependencies

TASK-003 through TASK-009 for available API contracts.

## Testing checklist

- [ ] Access token is not stored in localStorage.
- [ ] Protected route recovers after valid refresh.
- [ ] Refresh failure clears auth state and redirects safely.
- [ ] API error `request_id` is shown in support-friendly error UI.
- [ ] Catalog and circulation critical flows have tests.
- [ ] Frontend uses OpenAPI types and no duplicated endpoint string drift.
- [ ] Keyboard and basic screen-reader interaction works.

## Acceptance criteria

- User can login, browse catalog, submit/approve/checkout/return a loan and view notifications.
- Frontend does not make database calls or enforce authorization by itself.
- Nginx serves SPA assets and proxies `/api/` without exposing backend internals.

## Reviewer checklist

- [ ] No token is exposed to persistent browser storage.
- [ ] Every protected route has backend authorization counterpart.
- [ ] Error/loading/empty states are explicit.
- [ ] Client typing changes come from OpenAPI contract.
