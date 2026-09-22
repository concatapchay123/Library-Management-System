"""Protected HTTP adapter for bibliographic catalog titles."""

from __future__ import annotations

from typing import TypedDict
from uuid import UUID

from flask import Blueprint, Response, jsonify, request

from openlibrary.app.correlation import request_id
from openlibrary.modules.core.api.auth import (
    _principal_from_request,
    _require_principal,
)
from openlibrary.modules.core.application.access_tokens import AccessTokenService
from openlibrary.modules.core.application.books import (
    Book,
    BookCatalogService,
    BookPage,
)
from openlibrary.modules.core.infrastructure.tenancy import TenantRequestContext


class _BookPayload(TypedDict):
    title: str
    isbn: str | None
    authors: list[str]
    published_year: int | None


def create_books_blueprint(
    service: BookCatalogService,
    access_tokens: AccessTokenService,
    tenant_request_context: TenantRequestContext | None,
) -> Blueprint:
    """Expose catalog operations without accepting any tenant selector."""
    books = Blueprint("books", __name__, url_prefix="/api/v1/books")

    @books.get("")
    @_require_principal(access_tokens, tenant_request_context)
    def list_books() -> Response:
        try:
            result = service.list(
                actor=_principal_from_request(),
                limit=_limit(request.args.get("limit")),
                cursor=request.args.get("cursor"),
                filters={
                    key: value
                    for key, value in request.args.items()
                    if key not in {"limit", "cursor"}
                },
            )
        except ValueError:
            return _bad_request()
        return jsonify(_page_response(result))

    @books.post("")
    @_require_principal(access_tokens, tenant_request_context)
    def create_book() -> Response:
        try:
            book = service.create(actor=_principal_from_request(), **_book_payload())
        except ValueError:
            return _bad_request()
        response = jsonify(_book_response(book))
        response.status_code = 201
        return response

    @books.get("/<book_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def get_book(book_id: str) -> Response:
        try:
            parsed_book_id = UUID(book_id)
        except ValueError:
            return _bad_request()
        try:
            book = service.get(actor=_principal_from_request(), book_id=parsed_book_id)
        except KeyError:
            return _not_found()
        return jsonify(_book_response(book))

    @books.patch("/<book_id>")
    @_require_principal(access_tokens, tenant_request_context)
    def update_book(book_id: str) -> Response:
        try:
            book = service.update(
                actor=_principal_from_request(),
                book_id=UUID(book_id),
                **_book_payload(),
            )
        except ValueError:
            return _bad_request()
        except KeyError:
            return _not_found()
        return jsonify(_book_response(book))

    return books


def _limit(raw_value: str | None) -> int:
    if raw_value is None:
        return 20
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError("Invalid catalog page size") from error


def _book_payload() -> _BookPayload:
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        raise ValueError("Invalid book payload")
    required = {"title", "authors"}
    allowed = required | {"isbn", "published_year"}
    if set(payload) - allowed or not required <= set(payload):
        raise ValueError("Invalid book payload")
    title = payload["title"]
    authors = payload["authors"]
    isbn = payload.get("isbn")
    published_year = payload.get("published_year")
    if not isinstance(title, str) or not isinstance(authors, list):
        raise ValueError("Invalid book payload")
    if isbn is not None and not isinstance(isbn, str):
        raise ValueError("Invalid book payload")
    if published_year is not None and (
        isinstance(published_year, bool) or not isinstance(published_year, int)
    ):
        raise ValueError("Invalid book payload")
    cleaned_authors = [author for author in authors if isinstance(author, str)]
    if len(cleaned_authors) != len(authors):
        raise ValueError("Invalid book payload")
    return {
        "title": title,
        "authors": cleaned_authors,
        "isbn": isbn,
        "published_year": published_year,
    }


def _book_response(book: Book) -> dict[str, object]:
    return {
        "book_id": str(book.book_id),
        "title": book.title,
        "isbn": book.isbn,
        "authors": list(book.authors),
        "published_year": book.published_year,
    }


def _page_response(page: BookPage) -> dict[str, object]:
    return {
        "items": [_book_response(book) for book in page.items],
        "next_cursor": page.next_cursor,
    }


def _problem_response(status: int, title: str, detail: str) -> Response:
    response = jsonify(
        {
            "type": "https://openlibraryos.example/problems/"
            f"{'bad-request' if status == 400 else 'not-found'}",
            "title": title,
            "status": status,
            "detail": detail,
            "instance": request.path,
            "request_id": request_id(),
        }
    )
    response.status_code = status
    response.mimetype = "application/problem+json"
    return response


def _bad_request() -> Response:
    return _problem_response(400, "Bad Request", "Invalid catalog request.")


def _not_found() -> Response:
    return _problem_response(404, "Not Found", "The requested resource was not found.")
