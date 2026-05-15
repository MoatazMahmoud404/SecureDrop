from pathlib import Path

import backend_api.app.db as db


def test_init_db_creates_schema(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "securedrop.db")

    db.init_db()

    assert db.DB_PATH.exists()
    with db.get_connection() as connection:
        tables = {
            row[0]
            for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        }
        user_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
    assert {"users", "files", "pending_transfers", "audit_logs", "refresh_tokens", "shared_links"}.issubset(tables)
    assert {"failed_login_attempts", "locked_until", "role"}.issubset(user_columns)
