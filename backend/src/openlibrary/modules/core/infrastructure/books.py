"""SQL Server persistence for tenant-scoped bibliographic titles."""

from __future__ import annotations

import json
from contextlib import AbstractContextManager
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.engine import Connection, RowMapping

from openlibrary.modules.core.application.access_tokens import Principal
from openlibrary.modules.core.application.books import Book, BookStore
from openlibrary.modules.core.infrastructure.tenancy import SqlServerTenantContext


class SqlServerBookStore(BookStore):
    """Execute only parameterized, fixed-shape catalog SQL under tenant context."""

    def __init__(self, database_url: str) -> None:
        self._database_url = database_url
        self._tenant_context: SqlServerTenantContext | None = None

    def create(self, book: Book, *, actor: Principal) -> Book:
        with self._tenant_connection(actor.organization_id) as connection:
            connection.execute(
                text(
                    "INSERT INTO core.books (book_id, organization_id, title, "
                    "title_sort_key, isbn, authors_json, published_year) VALUES "
                    "(:book_id, :organization_id, :title, :title_sort_key, :isbn, "
                    ":authors_json, :published_year)"
                ),
                _book_params(book),
            )
        return book

    def get(self, organization_id: UUID, book_id: UUID) -> Book:
        with self._tenant_connection(organization_id) as connection:
            row = (
                connection.execute(
                    text(
                        "SELECT book_id, organization_id, title, title_sort_key, isbn, "
                        "authors_json, published_year FROM core.books "
                        "WHERE book_id = :book_id"
                    ),
                    {"book_id": str(book_id)},
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise KeyError(book_id)
        return _book_from_row(row)

    def update(self, book: Book, *, actor: Principal) -> Book:
        with self._tenant_connection(actor.organization_id) as connection:
            result = connection.execute(
                text(
                    "UPDATE core.books SET title = :title, title_sort_key = :title_sort_key, "
                    "isbn = :isbn, authors_json = :authors_json, "
                    "published_year = :published_year, updated_at = SYSUTCDATETIME() "
                    "WHERE book_id = :book_id"
                ),
                _book_params(book),
            )
        if result.rowcount != 1:
            raise KeyError(book.book_id)
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
        conditions = ["1 = 1"]
        params: dict[str, object] = {"limit": limit}
        if title is not None:
            conditions.append("title LIKE :title ESCAPE '\\'")
            params["title"] = f"%{_like(title)}%"
        if isbn is not None:
            conditions.append("isbn = :isbn")
            params["isbn"] = isbn
        if after is not None:
            conditions.append(
                "(title_sort_key > (SELECT title_sort_key FROM core.books "
                "WHERE book_id = :after_book_id) OR "
                "(title_sort_key = (SELECT title_sort_key FROM core.books "
                "WHERE book_id = :after_book_id) AND book_id > :after_book_id))"
            )
            params["after_book_id"] = str(after)
        statement = (
            "SELECT TOP (:limit) book_id, organization_id, title, title_sort_key, isbn, "
            "authors_json, published_year FROM core.books WHERE "
            + " AND ".join(conditions)
            + " ORDER BY title_sort_key, book_id"
        )
        with self._tenant_connection(organization_id) as connection:
            rows = connection.execute(text(statement), params).mappings()
            return [_book_from_row(row) for row in rows]

    def _tenant_connection(
        self, organization_id: UUID
    ) -> AbstractContextManager[Connection]:
        if self._tenant_context is None:
            self._tenant_context = SqlServerTenantContext(self._database_url)
        return self._tenant_context.connection(organization_id)


def _book_params(book: Book) -> dict[str, object]:
    return {
        "book_id": str(book.book_id),
        "organization_id": str(book.organization_id),
        "title": book.title,
        "title_sort_key": book.title_sort_key,
        "isbn": book.isbn,
        "authors_json": json.dumps(list(book.authors)),
        "published_year": book.published_year,
    }


def _book_from_row(row: RowMapping) -> Book:
    return Book(
        book_id=UUID(str(row["book_id"])),
        organization_id=UUID(str(row["organization_id"])),
        title=str(row["title"]),
        title_sort_key=str(row["title_sort_key"]),
        isbn=str(row["isbn"]) if row["isbn"] is not None else None,
        authors=tuple(json.loads(str(row["authors_json"]))),
        published_year=int(str(row["published_year"]))
        if row["published_year"] is not None
        else None,
    )


def _like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
