# TASK-007 — Education edition

## Task Information

- ID: TASK-007
- Name: Education module and borrower policies
- Priority: P2

## Objective

Add education-specific entities and policy resolution without placing education rules in the core circulation module.

## Scope

Implement students, teachers, departments, classes, courses, semesters, memberships and borrower policies. Default policy data is configurable: student maximum 5 books/14 days; teacher maximum 20 books/90 days.

## Files affected

- Create: `backend/src/openlibrary/modules/education/`
- Create: education migrations and tests
- Modify: `contracts/openapi/v1.yaml`, `docs/database-design.md`, `docs/architecture.md`
- Modify: frontend education feature after TASK-010 starts

## Implementation steps

1. Write failing tests for student/teacher policy resolution and semester date validation.
2. Run tests and confirm the module policy port is absent.
3. Implement education entities, repositories and policy resolver adapter.
4. Add tenant-scoped migrations and seed policies.
5. Connect core circulation through the policy interface, not education imports.
6. Add API permission checks and integration tests.

## Dependencies

TASK-006.

## Testing checklist

- [ ] Student default is 5 active loans and 14 days.
- [ ] Teacher default is 20 active loans and 90 days.
- [ ] Policies can be changed per organization without controller changes.
- [ ] Course/class/semester relations are tenant-scoped.
- [ ] Core package has no import dependency on education implementation.
- [ ] Policy snapshot is stored on loan at checkout.

## Acceptance criteria

- Education data can be enabled per organization.
- Borrower policy is selected by application service through a stable interface.
- Cross-tenant student/teacher access is blocked by RLS and authorization.

## Reviewer checklist

- [ ] Student/teacher numbers are tenant-unique.
- [ ] Date and enrollment invariants are tested.
- [ ] No education conditional branch is added to core domain entities.
- [ ] Defaults are seed data/configuration, not hidden constants in controllers.
