from __future__ import annotations

import io
import secrets
import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api.app.db as db
import backend_api.app.main as app_main
from backend_api.app.security import hash_password


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "securedrop-test.db")
    db.init_db()
    app_main.limiter.reset()

    uploaded_blobs: dict[str, bytes] = {}

    def fake_upload_file(
        socket_host: str,
        socket_port: int,
        token: str,
        file_name: str,
        file_stream,
        file_size: int,
    ) -> None:
        payload = file_stream.read()
        uploaded_blobs[file_name] = payload

        with db.get_connection() as connection:
            transfer = connection.execute(
                "SELECT user_id FROM pending_transfers WHERE token = ?",
                (token,),
            ).fetchone()
            assert transfer is not None
            connection.execute(
                "INSERT INTO files (id, owner_id, name, size, checksum_sha256, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    secrets.token_urlsafe(16),
                    transfer["user_id"],
                    file_name,
                    file_size,
                    hashlib.sha256(payload).hexdigest(),
                    app_main._now_iso(),
                ),
            )
            connection.execute(
                "UPDATE pending_transfers SET status = 'consumed' WHERE token = ?",
                (token,),
            )
            connection.commit()

    def fake_download_file(socket_host: str, socket_port: int, token: str, file_name: str):
        payload = uploaded_blobs.get(file_name, b"")
        yield payload

    monkeypatch.setattr(app_main, "upload_file", fake_upload_file)
    monkeypatch.setattr(app_main, "download_file", fake_download_file)

    with TestClient(app_main.app) as test_client:
        yield test_client


def _auth_headers(client: TestClient) -> dict[str, str]:
    username = f"user_{secrets.token_hex(4)}"
    password = "DemoPass123!"

    register_response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 200

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def _admin_auth_headers(client: TestClient) -> dict[str, str]:
    username = f"admin_{secrets.token_hex(4)}"
    password = "DemoPass123!"

    admin_id = secrets.token_urlsafe(16)
    password_salt, password_hash = hash_password(password)
    with db.get_connection() as connection:
        connection.execute(
            "INSERT INTO users (id, username, password_salt, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?, 'admin')",
            (admin_id, username, password_salt,
             password_hash, app_main._now_iso()),
        )
        connection.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    token = login_response.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


def test_api_upload_download_delete_flow(client: TestClient) -> None:
    headers = _auth_headers(client)

    payload = b"integration-test-payload"
    upload_response = client.post(
        "/api/upload-commit",
        files={"file": ("integration.txt", io.BytesIO(payload), "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 200

    files_response = client.get("/api/files", headers=headers)
    assert files_response.status_code == 200
    files = files_response.json()
    assert len(files) == 1
    assert files[0]["name"] == "integration.txt"
    assert files[0]["checksum_sha256"] == hashlib.sha256(payload).hexdigest()

    file_id = files[0]["id"]
    download_response = client.get(
        f"/api/download-commit/{file_id}", headers=headers)
    assert download_response.status_code == 200
    assert download_response.content == payload
    assert download_response.headers["x-file-checksum-sha256"] == hashlib.sha256(
        payload).hexdigest()

    delete_response = client.delete(f"/api/files/{file_id}", headers=headers)
    assert delete_response.status_code == 200

    activity_response = client.get("/api/user/activity", headers=headers)
    assert activity_response.status_code == 200
    activities = activity_response.json()
    assert len(activities) > 0
    actions = {entry["action"] for entry in activities}
    assert {"upload_commit", "download_commit",
            "delete_file"}.issubset(actions)


def test_upload_rejects_unsupported_extension(client: TestClient) -> None:
    headers = _auth_headers(client)

    response = client.post(
        "/api/upload-commit",
        files={"file": ("bad.exe", io.BytesIO(b"abc"),
                        "application/octet-stream")},
        headers=headers,
    )
    assert response.status_code == 400
    assert "Unsupported file type" in response.json()["detail"]


def test_upload_rejects_oversized_file(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = _auth_headers(client)
    monkeypatch.setattr(app_main, "MAX_UPLOAD_BYTES", 5)

    response = client.post(
        "/api/upload-commit",
        files={"file": ("big.txt", io.BytesIO(b"0123456789"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 413
    assert "File exceeds max size" in response.json()["detail"]


def test_upload_normalizes_filename_whitespace(client: TestClient) -> None:
    headers = _auth_headers(client)

    response = client.post(
        "/api/upload-commit",
        files={"file": ("my interview notes.txt",
                        io.BytesIO(b"abc"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 200
    assert response.json()["file_name"] == "my_interview_notes.txt"


def test_upload_commit_returns_502_on_socket_runtime_error(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = _auth_headers(client)

    def failing_upload_file(*args, **kwargs):
        raise RuntimeError(
            "ERROR invalid literal for int() with base 10: 'interview'")

    monkeypatch.setattr(app_main, "upload_file", failing_upload_file)

    response = client.post(
        "/api/upload-commit",
        files={"file": ("interview notes.txt",
                        io.BytesIO(b"abc"), "text/plain")},
        headers=headers,
    )
    assert response.status_code == 502
    assert "Upload failed" in response.json()["detail"]


def test_admin_audit_logs_requires_admin_role(client: TestClient) -> None:
    user_headers = _auth_headers(client)
    forbidden_response = client.get(
        "/api/admin/audit-logs", headers=user_headers)
    assert forbidden_response.status_code == 403

    admin_headers = _admin_auth_headers(client)
    allowed_response = client.get(
        "/api/admin/audit-logs", headers=admin_headers)
    assert allowed_response.status_code == 200
    assert isinstance(allowed_response.json(), list)


def test_share_link_download_with_password_and_limit(client: TestClient) -> None:
    headers = _auth_headers(client)

    payload = b"shareable-content"
    upload_response = client.post(
        "/api/upload-commit",
        files={"file": ("shared.txt", io.BytesIO(payload), "text/plain")},
        headers=headers,
    )
    assert upload_response.status_code == 200

    files_response = client.get("/api/files", headers=headers)
    assert files_response.status_code == 200
    file_id = files_response.json()[0]["id"]

    share_response = client.post(
        f"/api/files/{file_id}/share",
        json={"expires_in_minutes": 30, "max_downloads": 1,
              "password": "SharePass123!"},
        headers=headers,
    )
    assert share_response.status_code == 200
    share_data = share_response.json()
    token = share_data["token"]
    assert share_data["requires_password"] is True

    metadata_response = client.get(f"/api/share/{token}")
    assert metadata_response.status_code == 200
    metadata = metadata_response.json()
    assert metadata["file_id"] == file_id
    assert metadata["remaining_downloads"] == 1

    missing_password_response = client.post(
        f"/api/share/{token}/download",
        json={},
    )
    assert missing_password_response.status_code == 401

    wrong_password_response = client.post(
        f"/api/share/{token}/download",
        json={"password": "WrongPassword"},
    )
    assert wrong_password_response.status_code == 401

    download_response = client.post(
        f"/api/share/{token}/download",
        json={"password": "SharePass123!"},
    )
    assert download_response.status_code == 200
    assert download_response.content == payload

    expired_by_limit_response = client.get(f"/api/share/{token}")
    assert expired_by_limit_response.status_code == 410


def test_non_owner_cannot_create_share_link(client: TestClient) -> None:
    owner_headers = _auth_headers(client)

    payload = b"owner-only"
    upload_response = client.post(
        "/api/upload-commit",
        files={"file": ("private.txt", io.BytesIO(payload), "text/plain")},
        headers=owner_headers,
    )
    assert upload_response.status_code == 200

    files_response = client.get("/api/files", headers=owner_headers)
    assert files_response.status_code == 200
    file_id = files_response.json()[0]["id"]

    other_user_headers = _auth_headers(client)
    share_response = client.post(
        f"/api/files/{file_id}/share",
        json={"expires_in_minutes": 30},
        headers=other_user_headers,
    )
    assert share_response.status_code == 404


def test_2fa_status_and_disable_flow(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    headers = _auth_headers(client)

    initial_status = client.get("/api/auth/2fa-status", headers=headers)
    assert initial_status.status_code == 200
    assert initial_status.json()["enabled"] is False

    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    assert setup_response.status_code == 200
    otp_secret = setup_response.json()["otp_secret"]

    monkeypatch.setattr(app_main, "verify_otp_code", lambda secret, code: True)

    enable_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": otp_secret, "otp_code": "123456"},
        headers=headers,
    )
    assert enable_response.status_code == 200

    enabled_status = client.get("/api/auth/2fa-status", headers=headers)
    assert enabled_status.status_code == 200
    assert enabled_status.json()["enabled"] is True

    disable_response = client.post(
        "/api/auth/disable-2fa",
        json={"otp_code": "123456"},
        headers=headers,
    )
    assert disable_response.status_code == 200

    final_status = client.get("/api/auth/2fa-status", headers=headers)
    assert final_status.status_code == 200
    assert final_status.json()["enabled"] is False


def test_share_file_with_multiple_users(client: TestClient) -> None:
    owner_headers = _auth_headers(client)
    _ = _auth_headers(client)
    _ = _auth_headers(client)

    payload = b"multi-share-payload"
    upload_response = client.post(
        "/api/upload-commit",
        files={"file": ("group.txt", io.BytesIO(payload), "text/plain")},
        headers=owner_headers,
    )
    assert upload_response.status_code == 200

    files_response = client.get("/api/files", headers=owner_headers)
    assert files_response.status_code == 200
    file_id = files_response.json()[0]["id"]

    users_response = client.get("/api/users", headers=owner_headers)
    assert users_response.status_code == 200
    recipients = [row["username"] for row in users_response.json()]
    assert len(recipients) >= 2

    share_response = client.post(
        f"/api/files/{file_id}/share-users",
        json={
            "recipient_usernames": [recipients[0], recipients[1], "missing_user"],
            "permission": "download",
            "share_with_all_users": False,
        },
        headers=owner_headers,
    )
    assert share_response.status_code == 200
    payload = share_response.json()
    assert payload["created_count"] >= 2
    assert "missing_user" in payload["missing_usernames"]


def test_admin_user_crud(client: TestClient) -> None:
    admin_headers = _admin_auth_headers(client)

    create_response = client.post(
        "/api/admin/users",
        json={"username": "managed_user",
              "password": "ManagedPass123!", "role": "user"},
        headers=admin_headers,
    )
    assert create_response.status_code == 200
    created_user_id = create_response.json()["id"]

    list_response = client.get("/api/admin/users", headers=admin_headers)
    assert list_response.status_code == 200
    assert any(row["id"] == created_user_id for row in list_response.json())

    deactivate_response = client.patch(
        f"/api/admin/users/{created_user_id}",
        json={"is_active": False},
        headers=admin_headers,
    )
    assert deactivate_response.status_code == 200
    assert deactivate_response.json()["is_active"] is False

    delete_response = client.delete(
        f"/api/admin/users/{created_user_id}",
        headers=admin_headers,
    )
    assert delete_response.status_code == 200


def test_inactive_user_cannot_login(client: TestClient) -> None:
    username = "inactive_user"
    password = "DemoPass123!"

    register_response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 200

    with db.get_connection() as connection:
        connection.execute(
            "UPDATE users SET is_active = 0 WHERE username = ?",
            (username,),
        )
        connection.commit()

    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 403
