# TASK-001 — Architecture and repository governance

## Task Information

- ID: TASK-001
- Name: Architecture and repository governance
- Priority: P0 — blocking

## Objective

Establish the written architecture, product boundaries, security assumptions, development rules and task execution contract before application code begins.

## Scope

Include root governance files, all Phase 0 documents, Apache-2.0 license and target directory guidance. Do not create Flask, React, Docker runtime or database application code.

## Files affected

- Create: `AGENTS.md`, `RULES.md`, `DESIGN.md`, `LICENSE`, `README.md`
- Create: `docs/architecture.md`, `docs/system-design.md`, `docs/database-design.md`
- Create: `docs/api-design.md`, `docs/security.md`, `docs/deployment.md`
- Create: `docs/development-guide.md`, `docs/testing-strategy.md`, `docs/roadmap.md`

## Implementation steps

1. Record modular-monolith dependency direction and module boundaries.
2. Record shared SQL Server schema, tenant columns, RLS and connection context rules.
3. Record API versioning, auth, error, pagination and idempotency conventions.
4. Record security, deployment, testing and migration policy.
5. Add task files with independent checkpoints.
6. Scan documents for unresolved placeholders and contradictions.

## Dependencies

None.

## Testing checklist

- [ ] Every required document exists.
- [ ] `organization_id` and RLS rules agree across architecture, database and security docs.
- [ ] Module names agree across design, roadmap and task files.
- [ ] No unresolved planning marker or incomplete section remains.
- [ ] All internal links resolve.

## Acceptance criteria

- A new contributor can identify repository structure, dependency direction, security boundary and first implementation task without oral context.
- The plan explicitly excludes microservices and application code from Phase 0.
- Every later phase has a measurable checkpoint.

## Reviewer checklist

- [ ] No business rule is hidden only in a task title.
- [ ] No document permits controller-level business logic or app-only tenant isolation.
- [ ] Security and testing requirements are actionable.
- [ ] License and contribution assumptions are visible.
