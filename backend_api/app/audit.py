from __future__ import annotations

import datetime as dt
import json
import secrets

from fastapi import Request

from backend_api.app.db import get_connection


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip() or None
    if request.client is not None:
        return request.client.host
    return None


def _user_agent(request: Request | None) -> str | None:
    if request is None:
        return None
    return request.headers.get("user-agent")


def log_audit_event(
    *,
    action: str,
    status: str,
    request: Request | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    resource_id: str | None = None,
    details: dict | None = None,
) -> None:
    """Persist audit event without breaking request flow on logging failure."""
    try:
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO audit_logs (id, user_id, action, resource_type, resource_id, status, ip_address, user_agent, timestamp, details)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    secrets.token_urlsafe(16),
                    user_id,
                    action,
                    resource_type,
                    resource_id,
                    status,
                    _client_ip(request),
                    _user_agent(request),
                    _now_iso(),
                    json.dumps(details) if details is not None else None,
                ),
            )
            connection.commit()
    except Exception:
        # Audit logging should not prevent core API operations.
        return
