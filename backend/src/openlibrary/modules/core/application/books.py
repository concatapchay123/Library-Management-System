"""Tenant-scoped bibliographic catalog use cases."""

from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID, uuid4

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.authorization import AuthorizationPort


@dataclass(frozen=True, slots=True)
class Book:
    """A bibliographic title, deliberately separate from any physical copy."""

    book_id: UUID
    organization_id: UUID
    title: str
    title_sort_key: str
    isbn: str | None
    authors: tuple[str, ...]
    published_year: int | None


@dataclass(frozen=True, slots=True)
class BookPage:
    """One stable page of catalog titles."""

    items: tuple[Book, ...]
    next_cursor: str | None


class BookStore(Protocol):
    """Persistence that is always called with the verified tenant identity."""

    def create(self, book: Book, *, actor: Principal) -> Book: ...

    def get(self, organization_id: UUID, book_id: UUID) -> Book: ...

    def update(self, book: Book, *, actor: Principal) -> Book: ...

    def list(
        self,
        organization_id: UUID,
        *,
        title: str | None,
        isbn: str | None,
        after: UUID | None,
        limit: int,
    ) -> list[Book]: ...


class BookCatalogService:
    """Own catalog authorization, validation and cursor policy at the use-case boundary."""

    _READ_PERMISSION = "catalog.read"
    _MANAGE_PERMISSION = "catalog.manage"
    _ALLOWED_FILTERS = frozenset({"title", "isbn"})
    _MAX_PAGE_SIZE = 100

    def __init__(self, store: BookStore, authorizer: AuthorizationPort) -> None:
        self._store = store
        self._authorizer = authorizer

    def create(
        self,
        *,
        actor: Principal,
        title: str,
        isbn: str | None,
        authors: list[str],
        published_year: int | None,
    ) -> Book:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)
        cleaned_title = _title(title)
        return self._store.create(
            Book(
                book_id=uuid4(),
                organization_id=actor.organization_id,
                title=cleaned_title,
                title_sort_key=catalog_sort_key(cleaned_title),
                isbn=_isbn(isbn),
                authors=_authors(authors),
                published_year=_published_year(published_year),
            ),
            actor=actor,
        )

    def update(
        self,
        *,
        actor: Principal,
        book_id: UUID,
        title: str,
        isbn: str | None,
        authors: list[str],
        published_year: int | None,
    ) -> Book:
        self._authorizer.require(actor, self._MANAGE_PERMISSION)
        # Loading by the actor tenant makes a foreign id indistinguishable from absent.
        self._store.get(actor.organization_id, book_id)
        cleaned_title = _title(title)
        return self._store.update(
            Book(
                book_id=book_id,
                organization_id=actor.organization_id,
                title=cleaned_title,
                title_sort_key=catalog_sort_key(cleaned_title),
                isbn=_isbn(isbn),
                authors=_authors(authors),
                published_year=_published_year(published_year),
            ),
            actor=actor,
        )

    def get(self, *, actor: Principal, book_id: UUID) -> Book:
        self._authorizer.require(actor, self._READ_PERMISSION)
        return self._store.get(actor.organization_id, book_id)

    def list(
        self,
        *,
        actor: Principal,
        limit: int,
        cursor: str | None,
        filters: dict[str, str],
    ) -> BookPage:
        self._authorizer.require(actor, self._READ_PERMISSION)
        unsupported = set(filters) - self._ALLOWED_FILTERS
        if unsupported:
            raise ValueError("Unsupported catalog filter")
        if not 1 <= limit <= self._MAX_PAGE_SIZE:
            raise ValueError("Invalid catalog page size")
        title = _filter(filters.get("title"), "title")
        isbn = _filter(filters.get("isbn"), "isbn")
        items = self._store.list(
            actor.organization_id,
            title=title,
            isbn=isbn,
            after=_decode_cursor(cursor),
            limit=limit + 1,
        )
        page_items = tuple(items[:limit])
        next_cursor = (
            _encode_cursor(page_items[-1])
            if len(items) > limit and page_items
            else None
        )
        return BookPage(items=page_items, next_cursor=next_cursor)


def _title(value: str) -> str:
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned or _utf16_units(cleaned) > 512:
        raise ValueError("Invalid book title")
    return cleaned


def _isbn(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip() if isinstance(value, str) else ""
    if not cleaned or len(cleaned) > 32:
        raise ValueError("Invalid ISBN")
    return cleaned


def _authors(value: list[str]) -> tuple[str, ...]:
    if not isinstance(value, list) or not value or len(value) > 32:
        raise ValueError("Invalid book authors")
    cleaned = tuple(author.strip() for author in value if isinstance(author, str))
    if len(cleaned) != len(value) or any(
        not author or len(author) > 256 for author in cleaned
    ):
        raise ValueError("Invalid book authors")
    return cleaned


def _published_year(value: int | None) -> int | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 9999:
        raise ValueError("Invalid publication year")
    return value


def _filter(value: str | None, name: str) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned or len(cleaned) > (512 if name == "title" else 32):
        raise ValueError(f"Invalid {name} filter")
    return cleaned


def _encode_cursor(book: Book) -> str:
    """Encode only the stable id; SQL resolves its ordering key under RLS."""
    return base64.urlsafe_b64encode(str(book.book_id).encode()).decode().rstrip("=")


def _decode_cursor(cursor: str | None) -> UUID | None:
    if cursor is None:
        return None
    if not isinstance(cursor, str) or not cursor or len(cursor) > 64:
        raise ValueError("Invalid catalog cursor")
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        return UUID(base64.urlsafe_b64decode(padded.encode()).decode())
    except (UnicodeDecodeError, ValueError) as error:
        raise ValueError("Invalid catalog cursor") from error


def catalog_sort_key(title: str) -> str:
    """Return the persisted binary-order key shared by cursor encoding and SQL."""
    key = title.casefold()
    if _utf16_units(key) > 834:
        raise ValueError("Invalid book title")
    return key


def _utf16_units(value: str) -> int:
    return len(value.encode("utf-16-le")) // 2
