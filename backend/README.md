# Backend package

Backend Phase 1 bắt đầu với Flask app factory và health endpoints theo [kiến trúc](../docs/architecture.md). SQLAlchemy integration, migrations và business modules được bổ sung ở các task backend kế tiếp.

## Thiết lập

```powershell
python -m pip install -e ".[dev]"
```

## Lệnh kiểm tra chuẩn

Chạy từ thư mục `backend`:

```powershell
python -m pytest -q
python -m ruff check .
python -m mypy src
```
