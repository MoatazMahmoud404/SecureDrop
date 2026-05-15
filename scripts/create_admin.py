from __future__ import annotations
from backend_api.app.security import hash_password
from backend_api.app.db import get_connection, init_db

import argparse
import datetime as dt
import getpass
import secrets
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_password(provided_password: str | None, username: str) -> str:
    if provided_password:
        return provided_password

    first = getpass.getpass(f"Enter password for '{username}': ")
    second = getpass.getpass("Confirm password: ")
    if first != second:
        raise ValueError("Passwords do not match")
    if len(first) < 8:
        raise ValueError("Password must be at least 8 characters")
    return first


def create_or_promote_admin(username: str, password: str | None, set_password: bool) -> str:
    init_db()

    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if existing is None:
            resolved_password = _read_password(password, username)
            password_salt, password_hash = hash_password(resolved_password)
            connection.execute(
                """
                INSERT INTO users (id, username, password_salt, password_hash, created_at, role)
                VALUES (?, ?, ?, ?, ?, 'admin')
                """,
                (secrets.token_urlsafe(16), username,
                 password_salt, password_hash, _now_iso()),
            )
            connection.commit()
            return f"Created new admin account: {username}"

        updates: list[str] = []
        params: list[str] = []

        if existing["role"] != "admin":
            updates.append("role = 'admin'")

        if set_password:
            resolved_password = _read_password(password, username)
            password_salt, password_hash = hash_password(resolved_password)
            updates.extend(["password_salt = ?", "password_hash = ?"])
            params.extend([password_salt, password_hash])

        if not updates:
            return f"User '{username}' is already an admin. No changes made."

        params.append(username)
        connection.execute(
            f"UPDATE users SET {', '.join(updates)} WHERE username = ?",
            tuple(params),
        )
        connection.commit()

        if set_password:
            return f"Promoted '{username}' to admin and updated password."
        return f"Promoted '{username}' to admin."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a new SecureDrop admin account or promote an existing user to admin.",
    )
    parser.add_argument("username", help="Username to create/promote")
    parser.add_argument(
        "--password",
        help="Password for new admin or password reset. If omitted, script prompts securely.",
    )
    parser.add_argument(
        "--set-password",
        action="store_true",
        help="When user already exists, reset password in addition to promoting to admin.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    message = create_or_promote_admin(
        username=args.username,
        password=args.password,
        set_password=args.set_password,
    )
    print(message)


if __name__ == "__main__":
    main()
