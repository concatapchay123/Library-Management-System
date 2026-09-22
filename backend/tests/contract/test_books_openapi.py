"""Consumer contract for catalog titles and cursor listing."""

import json
from pathlib import Path


def load_contract() -> dict[str, object]:
    path = Path(__file__).resolve().parents[3] / "contracts" / "openapi" / "v1.yaml"
    return json.loads(path.read_text(encoding="utf-8"))


def test_books_contract_exposes_tenant_scoped_list_create_get_and_update() -> None:
    contract = load_contract()
    paths = contract["paths"]

    assert {"get", "post"} <= set(paths["/books"])
    assert {"get", "patch"} <= set(paths["/books/{book_id}"])
    assert paths["/books"]["get"]["responses"]["200"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/BookPage"}
    assert paths["/books"]["post"]["responses"]["201"]["content"]["application/json"][
        "schema"
    ] == {"$ref": "#/components/schemas/Book"}
    assert "400" in paths["/books/{book_id}"]["get"]["responses"]

    schemas = contract["components"]["schemas"]
    assert schemas["BookPage"]["required"] == ["items", "next_cursor"]
    assert schemas["Book"]["required"] == ["book_id", "title", "authors"]
