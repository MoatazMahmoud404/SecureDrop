from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import backend_api.app.db as db
import backend_api.app.main as app_main


@pytest.fixture()
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "securedrop-test.db")
    db.init_db()
    app_main.limiter.reset()

    with TestClient(app_main.app) as test_client:
        yield test_client


def _register_and_login(client: TestClient) -> tuple[str, str, dict]:
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
    return username, password, login_response.json()


def test_login_returns_refresh_token(client: TestClient) -> None:
    _, _, login_data = _register_and_login(client)

    assert login_data["requires_2fa"] is False
    assert "access_token" in login_data
    assert login_data.get("token_type") == "bearer"
    assert "refresh_token" in login_data
    assert isinstance(login_data["refresh_token"], str)


def test_refresh_rotates_refresh_token(client: TestClient) -> None:
    _, _, login_data = _register_and_login(client)

    original_refresh = login_data["refresh_token"]
    refresh_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert refresh_response.status_code == 200
    refresh_data = refresh_response.json()

    assert "access_token" in refresh_data
    assert "refresh_token" in refresh_data
    assert refresh_data["refresh_token"] != original_refresh

    reuse_response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": original_refresh},
    )
    assert reuse_response.status_code == 401


def test_logout_revokes_refresh_token(client: TestClient) -> None:
    _, _, login_data = _register_and_login(client)
    refresh_token = login_data["refresh_token"]

    logout_response = client.post(
        "/api/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_response.status_code == 200

    refresh_after_logout = client.post(
        "/api/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_after_logout.status_code == 401


def test_refresh_rejects_access_token(client: TestClient) -> None:
    _, _, login_data = _register_and_login(client)

    response = client.post(
        "/api/auth/refresh",
        json={"refresh_token": login_data["access_token"]},
    )
    assert response.status_code == 401
