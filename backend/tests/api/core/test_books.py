"""Contract tests for the tenant-scoped bibliographic catalog."""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest

from openlibrary.app.config import AppConfig
from openlibrary.app.factory import create_app
from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationDenied
from openlibrary.modules.core.application.books import Book, BookCatalogService


ORGANIZATION_A = uuid4()
ORGANIZATION_B = uuid4()
ACTOR_A = Principal(uuid4(), ORGANIZATION_A, uuid4())
ACTOR_B = Principal(uuid4(), ORGANIZATION_B, uuid4())


@dataclass
class _BookStore:
    books: dict[UUID, Book] = field(default_factory=dict)

    def create(self, book: Book, *, actor: Principal) -> Book:
        assert book.organization_id == actor.organization_id
        self.books[book.book_id] = book
        return book

    def get(self, organization_id: UUID, book_id: UUID) -> Book:
        book = self.books.get(book_id)
        if book is None or book.organization_id != organization_id:
            raise KeyError(book_id)
        return book

    def update(self, book: Book, *, actor: Principal) -> Book:
        assert book.organization_id == actor.organization_id
        if book.book_id not in self.books:
            raise KeyError(book.book_id)
        self.books[book.book_id] = book
        return book

    def list(
        self,
        organization_id: UUID,
        *,
        title: str | None,
        isbn: str | None,
        after: UUID | None,
        limit: int,
    ) -> list[Book]:
        filtered = [
            book
            for book in self.books.values()
            if book.organization_id == organization_id
            and (title is None or title.casefold() in book.title.casefold())
            and (isbn is None or isbn == book.isbn)
        ]
        ordered = sorted(
            filtered, key=lambda book: (book.title_sort_key, str(book.book_id))
        )
        if after is not None:
            anchor = self.books.get(after)
            if anchor is None or anchor.organization_id != organization_id:
                return []
            ordered = [
                book
                for book in ordered
                if (book.title_sort_key, str(book.book_id))
                > (anchor.title_sort_key, str(anchor.book_id))
            ]
        return ordered[:limit]


class _Authorizer:
    def __init__(self, allowed: set[str]) -> None:
        self.allowed = allowed

    def require(self, principal: Principal, permission: str) -> None:
        if permission not in self.allowed:
            raise AuthorizationDenied("denied")


class _AccessTokens:
    def verify(self, token: str) -> Principal:
        return {"tenant-a": ACTOR_A, "tenant-b": ACTOR_B}[token]


def _book(title: str, *, organization_id: UUID = ORGANIZATION_A) -> Book:
    return Book(
        book_id=uuid4(),
        organization_id=organization_id,
        title=title,
        title_sort_key=title.casefold(),
        isbn=None,
        authors=("Author",),
        published_year=None,
    )


def test_catalog_list_is_tenant_scoped_and_cursor_is_stable() -> None:
    store = _BookStore()
    service = BookCatalogService(store, _Authorizer({"catalog.read", "catalog.manage"}))
    alpha = service.create(
        actor=ACTOR_A, title="Alpha", isbn=None, authors=["A"], published_year=None
    )
    bravo = service.create(
        actor=ACTOR_A, title="Bravo", isbn=None, authors=["B"], published_year=None
    )
    service.create(
        actor=ACTOR_B,
        title="Other tenant",
        isbn=None,
        authors=["C"],
        published_year=None,
    )

    first = service.list(actor=ACTOR_A, limit=1, cursor=None, filters={})
    second = service.list(actor=ACTOR_A, limit=1, cursor=first.next_cursor, filters={})

    assert first.items == (alpha,)
    assert second.items == (bravo,)
    assert second.next_cursor is None


def test_catalog_cursor_does_not_contain_a_raw_title() -> None:
    store = _BookStore()
    service = BookCatalogService(store, _Authorizer({"catalog.read", "catalog.manage"}))
    service.create(
        actor=ACTOR_A,
        title="Private bibliographic title",
        isbn=None,
        authors=["A"],
        published_year=None,
    )
    service.create(
        actor=ACTOR_A,
        title="Second title",
        isbn=None,
        authors=["B"],
        published_year=None,
    )

    cursor = service.list(actor=ACTOR_A, limit=1, cursor=None, filters={}).next_cursor

    assert cursor is not None
    decoded = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
    assert "Private bibliographic title" not in decoded


def test_catalog_cursor_for_a_long_unicode_title_is_reusable() -> None:
    store = _BookStore()
    service = BookCatalogService(store, _Authorizer({"catalog.read", "catalog.manage"}))
    service.create(
        actor=ACTOR_A,
        title="\u4e2d" * 512,
        isbn=None,
        authors=["A"],
        published_year=None,
    )
    service.create(
        actor=ACTOR_A,
        title="\u4e2d" * 511 + "\u4e59",
        isbn=None,
        authors=["B"],
        published_year=None,
    )

    first = service.list(actor=ACTOR_A, limit=1, cursor=None, filters={})

    assert first.next_cursor is not None
    assert len(first.next_cursor) <= 64
    assert service.list(
        actor=ACTOR_A, limit=1, cursor=first.next_cursor, filters={}
    ).items


def test_catalog_persists_a_casefolded_title_sort_key() -> None:
    service = BookCatalogService(_BookStore(), _Authorizer({"catalog.manage"}))

    created = service.create(
        actor=ACTOR_A,
        title="Straße",
        isbn=None,
        authors=["Author"],
        published_year=None,
    )

    assert created.title_sort_key == "strasse"


def test_catalog_derives_its_sort_key_from_the_normalized_title() -> None:
    service = BookCatalogService(_BookStore(), _Authorizer({"catalog.manage"}))

    created = service.create(
        actor=ACTOR_A,
        title="  Straße  ",
        isbn=None,
        authors=["Author"],
        published_year=None,
    )

    assert created.title == "Straße"
    assert created.title_sort_key == "strasse"


def test_catalog_rejects_a_casefolded_sort_key_that_cannot_be_indexed() -> None:
    service = BookCatalogService(_BookStore(), _Authorizer({"catalog.manage"}))

    with pytest.raises(ValueError, match="Invalid book title"):
        service.create(
            actor=ACTOR_A,
            title="\u0390" * 512,
            isbn=None,
            authors=["Author"],
            published_year=None,
        )


def test_catalog_rejects_unsupported_filter_before_store_query() -> None:
    service = BookCatalogService(_BookStore(), _Authorizer({"catalog.read"}))

    with pytest.raises(ValueError, match="Unsupported catalog filter"):
        service.list(
            actor=ACTOR_A, limit=20, cursor=None, filters={"sort": "drop table"}
        )


def test_catalog_update_cannot_cross_a_tenant_boundary() -> None:
    store = _BookStore()
    service = BookCatalogService(store, _Authorizer({"catalog.read", "catalog.manage"}))
    book = service.create(
        actor=ACTOR_A,
        title="Original",
        isbn=None,
        authors=["Author"],
        published_year=None,
    )

    with pytest.raises(KeyError):
        service.update(
            actor=ACTOR_B,
            book_id=book.book_id,
            title="Cross tenant",
            isbn=None,
            authors=["Author"],
            published_year=None,
        )

    assert store.books[book.book_id].title == "Original"


def test_catalog_requires_named_read_and_manage_permissions() -> None:
    read_only = BookCatalogService(_BookStore(), _Authorizer({"catalog.read"}))
    manage_only = BookCatalogService(_BookStore(), _Authorizer({"catalog.manage"}))

    with pytest.raises(AuthorizationDenied):
        read_only.create(
            actor=ACTOR_A,
            title="Denied",
            isbn=None,
            authors=["Author"],
            published_year=None,
        )
    with pytest.raises(AuthorizationDenied):
        manage_only.list(actor=ACTOR_A, limit=20, cursor=None, filters={})


def test_books_http_routes_enforce_catalog_permissions_and_derive_tenant_from_token() -> (
    None
):
    store = _BookStore()
    service = BookCatalogService(store, _Authorizer({"catalog.read", "catalog.manage"}))
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_AccessTokens(),  # type: ignore[arg-type]
            book_catalog=service,
        )
    )
    client = app.test_client()

    created = client.post(
        "/api/v1/books",
        headers={"Authorization": "Bearer tenant-a"},
        json={"title": "Tenant A title", "authors": ["Author"]},
    )
    tenant_b_list = client.get(
        "/api/v1/books",
        headers={"Authorization": "Bearer tenant-b"},
    )

    assert created.status_code == 201
    assert tenant_b_list.get_json() == {"items": [], "next_cursor": None}


def test_book_get_rejects_a_malformed_identifier_as_bad_request() -> None:
    service = BookCatalogService(_BookStore(), _Authorizer({"catalog.read"}))
    app = create_app(
        AppConfig(
            readiness_probe=lambda: True,
            access_tokens=_AccessTokens(),  # type: ignore[arg-type]
            book_catalog=service,
        )
    )

    response = app.test_client().get(
        "/api/v1/books/not-a-uuid", headers={"Authorization": "Bearer tenant-a"}
    )

    assert response.status_code == 400
    assert response.mimetype == "application/problem+json"
