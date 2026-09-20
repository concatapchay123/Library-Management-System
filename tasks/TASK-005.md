# TASK-005 — Book catalog and inventory

## Task Information

- ID: TASK-005
- Name: Books, copies, barcodes and locations
- Priority: P1

## Objective

Implement the catalog and physical inventory model that distinguishes a bibliographic book from its individually tracked copies.

## Scope

Implement `core.books`, `core.book_copies`, `core.locations` and `core.copy_status_history`. Support barcode uniqueness, copy condition, location and statuses `available`, `borrowed`, `lost`, `damaged`, `maintenance`.

## Files affected

- Modify: `backend/src/openlibrary/modules/core/`
- Create: catalog/inventory migrations and tests
- Modify: `contracts/openapi/v1.yaml`, `docs/database-design.md`, `docs/api-design.md`
- Later frontend integration: `frontend/src/features/catalog/`

## Implementation steps

1. Write failing unit tests for copy status transition rules and duplicate barcode rejection.
2. Run tests and confirm missing domain policy causes expected failures.
3. Implement book/copy/location entities and repository adapters.
4. Add migration, tenant-prefixed indexes and status history append behavior.
5. Add API schemas, permission checks and cursor search for books.
6. Add integration tests for concurrent status updates and tenant isolation.

## Dependencies

TASK-004.

## Testing checklist

- [ ] Book title can have multiple copies.
- [ ] Barcode is unique within organization.
- [ ] Copy cannot checkout from lost/damaged/maintenance.
- [ ] Status transition records actor, reason and timestamp.
- [ ] Location hierarchy remains tenant-scoped.
- [ ] Catalog search does not expose another organization.

## Acceptance criteria

- Librarian can create a book, register copies, assign locations and change condition/status.
- Inventory state history is append-only and queryable.
- API rejects invalid transitions with stable problem type.

## Reviewer checklist

- [ ] No book-level status is used where copy-level status is required.
- [ ] Status transition is transactional with its audit event.
- [ ] Search filters are allow-listed and parameterized.
- [ ] Indexes match documented tenant-first strategy.
