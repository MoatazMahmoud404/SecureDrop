from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "securedrop.db"


SCHEMA = """
PRAGMA journal_mode=WAL;

CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    password_salt TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'user',
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    otp_secret TEXT,
    otp_enabled BOOLEAN DEFAULT FALSE,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);

CREATE TABLE IF NOT EXISTS files (
    id TEXT PRIMARY KEY,
    owner_id TEXT NOT NULL,
    name TEXT NOT NULL,
    size INTEGER NOT NULL,
    checksum_sha256 TEXT,
    uploaded_at TEXT NOT NULL,
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS pending_transfers (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    action TEXT NOT NULL,
    file_id TEXT,
    file_name TEXT,
    file_size INTEGER,
    created_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS audit_logs (
    id TEXT PRIMARY KEY,
    user_id TEXT,
    action TEXT NOT NULL,
    resource_type TEXT,
    resource_id TEXT,
    status TEXT NOT NULL,
    ip_address TEXT,
    user_agent TEXT,
    timestamp TEXT NOT NULL,
    details TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS refresh_tokens (
    token TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (user_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS shared_links (
    token TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    password_salt TEXT,
    password_hash TEXT,
    expires_at TEXT NOT NULL,
    max_downloads INTEGER NOT NULL DEFAULT -1,
    download_count INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL,
    revoked BOOLEAN NOT NULL DEFAULT FALSE,
    FOREIGN KEY (file_id) REFERENCES files(id),
    FOREIGN KEY (owner_id) REFERENCES users(id)
);

CREATE TABLE IF NOT EXISTS file_shares (
    id TEXT PRIMARY KEY,
    file_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    recipient_id TEXT NOT NULL,
    permission TEXT NOT NULL,
    password_salt TEXT,
    password_hash TEXT,
    created_at TEXT NOT NULL,
    UNIQUE(file_id, recipient_id),
    FOREIGN KEY (file_id) REFERENCES files(id),
    FOREIGN KEY (owner_id) REFERENCES users(id),
    FOREIGN KEY (recipient_id) REFERENCES users(id)
);
"""


def init_db() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(DB_PATH) as connection:
        connection.executescript(SCHEMA)
        # Keep existing local DBs compatible when new columns are introduced.
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(files)").fetchall()
        }
        if "checksum_sha256" not in columns:
            connection.execute(
                "ALTER TABLE files ADD COLUMN checksum_sha256 TEXT")

        # Add OTP columns if they don't exist
        user_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(users)").fetchall()
        }
        if "otp_secret" not in user_columns:
            connection.execute("ALTER TABLE users ADD COLUMN otp_secret TEXT")
        if "otp_enabled" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN otp_enabled BOOLEAN DEFAULT FALSE")
        if "failed_login_attempts" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN failed_login_attempts INTEGER NOT NULL DEFAULT 0"
            )
        if "locked_until" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN locked_until TEXT")
        if "role" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'"
            )
        if "is_active" not in user_columns:
            connection.execute(
                "ALTER TABLE users ADD COLUMN is_active BOOLEAN NOT NULL DEFAULT TRUE"
            )

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        if "audit_logs" not in tables:
            connection.execute(
                """
                CREATE TABLE audit_logs (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    action TEXT NOT NULL,
                    resource_type TEXT,
                    resource_id TEXT,
                    status TEXT NOT NULL,
                    ip_address TEXT,
                    user_agent TEXT,
                    timestamp TEXT NOT NULL,
                    details TEXT,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )

        if "refresh_tokens" not in tables:
            connection.execute(
                """
                CREATE TABLE refresh_tokens (
                    token TEXT PRIMARY KEY,
                    user_id TEXT NOT NULL,
                    issued_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    revoked BOOLEAN NOT NULL DEFAULT FALSE,
                    FOREIGN KEY (user_id) REFERENCES users(id)
                )
                """
            )

        if "shared_links" not in tables:
            connection.execute(
                """
                CREATE TABLE shared_links (
                    token TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    password_salt TEXT,
                    password_hash TEXT,
                    expires_at TEXT NOT NULL,
                    max_downloads INTEGER NOT NULL DEFAULT -1,
                    download_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    revoked BOOLEAN NOT NULL DEFAULT FALSE,
                    FOREIGN KEY (file_id) REFERENCES files(id),
                    FOREIGN KEY (owner_id) REFERENCES users(id)
                )
                """
            )

        if "file_shares" not in tables:
            connection.execute(
                """
                CREATE TABLE file_shares (
                    id TEXT PRIMARY KEY,
                    file_id TEXT NOT NULL,
                    owner_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    permission TEXT NOT NULL,
                    password_salt TEXT,
                    password_hash TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(file_id, recipient_id),
                    FOREIGN KEY (file_id) REFERENCES files(id),
                    FOREIGN KEY (owner_id) REFERENCES users(id),
                    FOREIGN KEY (recipient_id) REFERENCES users(id)
                )
                """
            )
        else:
            file_share_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(file_shares)").fetchall()
            }
            if "password_salt" not in file_share_columns:
                connection.execute(
                    "ALTER TABLE file_shares ADD COLUMN password_salt TEXT")
            if "password_hash" not in file_share_columns:
                connection.execute(
                    "ALTER TABLE file_shares ADD COLUMN password_hash TEXT")

        connection.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    init_db()
    connection = sqlite3.connect(DB_PATH)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
    finally:
        connection.close()
