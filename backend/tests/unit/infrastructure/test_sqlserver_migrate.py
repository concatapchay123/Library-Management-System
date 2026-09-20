"""Unit tests for SQL Server migration URL handling."""

from sqlalchemy.engine import make_url

from openlibrary.infrastructure.sqlserver.migrate import database_url_for


def test_database_url_for_preserves_a_valid_hyphenated_database_name() -> None:
    """Database names are connection data, not identifiers interpolated into SQL."""
    url = database_url_for(
        "mssql+pyodbc://migrator:password@example.test/master?"
        "driver=ODBC+Driver+18+for+SQL+Server",
        "library-development",
    )

    assert make_url(url).database == "library-development"
