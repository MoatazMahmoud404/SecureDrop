"""Tests for 2FA/OTP functionality."""
from __future__ import annotations

import datetime as dt
import secrets
import re

import pytest
import pyotp
from fastapi.testclient import TestClient

import backend_api.app.db as db
import backend_api.app.main as app_main


@pytest.fixture()
def client(tmp_path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setattr(db, "DATA_DIR", tmp_path)
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "securedrop-test.db")
    db.init_db()
    app_main.limiter.reset()

    with TestClient(app_main.app) as test_client:
        yield test_client


def _register_and_login(client: TestClient) -> tuple[str, str, dict[str, str]]:
    """Register a user and return username, password, and auth headers."""
    username = f"user_{secrets.token_hex(4)}"
    password = "DemoPass123!"

    # Register
    register_response = client.post(
        "/api/auth/register",
        json={"username": username, "password": password},
    )
    assert register_response.status_code == 200

    # Login (no 2FA)
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()

    # Should not require 2FA for new user
    assert login_data.get("requires_2fa") is False
    token = login_data["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    return username, password, headers


def test_setup_2fa_endpoint(client: TestClient) -> None:
    """Test 2FA setup endpoint returns secret and QR code."""
    _, _, headers = _register_and_login(client)

    response = client.post("/api/auth/setup-2fa", headers=headers)
    assert response.status_code == 200

    data = response.json()
    assert "otp_secret" in data
    assert "qr_code_data_url" in data
    assert data["qr_code_data_url"].startswith("data:image/png;base64,")

    # Verify the secret is valid Base32
    secret = data["otp_secret"]
    assert len(secret) >= 26  # Base32 encoded should be at least 26 chars

    # Verify we can create a TOTP object from it
    totp = pyotp.TOTP(secret)
    assert totp.provisioning_uri() is not None


def test_verify_2fa_activates_for_user(client: TestClient) -> None:
    """Test 2FA verification activates 2FA for the user."""
    _, _, headers = _register_and_login(client)

    # Setup 2FA
    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    assert setup_response.status_code == 200
    secret = setup_response.json()["otp_secret"]

    # Generate OTP code
    totp = pyotp.TOTP(secret)
    otp_code = totp.now()

    # Verify 2FA
    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": otp_code},
        headers=headers,
    )
    assert verify_response.status_code == 200
    assert verify_response.json()["status"] == "success"


def test_verify_2fa_rejects_invalid_otp(client: TestClient) -> None:
    """Test 2FA verification rejects invalid OTP code."""
    _, _, headers = _register_and_login(client)

    # Setup 2FA
    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    assert setup_response.status_code == 200
    secret = setup_response.json()["otp_secret"]

    # Try to verify with wrong OTP
    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": "000000"},
        headers=headers,
    )
    assert verify_response.status_code == 401
    assert "Invalid OTP" in verify_response.json()["detail"]


def test_login_requires_2fa_after_activation(client: TestClient) -> None:
    """Test that login requires 2FA after it's enabled."""
    username, password, headers = _register_and_login(client)

    # Setup and verify 2FA
    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    secret = setup_response.json()["otp_secret"]

    totp = pyotp.TOTP(secret)
    otp_code = totp.now()

    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": otp_code},
        headers=headers,
    )
    assert verify_response.status_code == 200

    # Try to login again
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()

    # Should require 2FA
    assert login_data["requires_2fa"] is True
    assert "temp_token" in login_data
    assert login_data.get("access_token") is None


def test_login_with_2fa_flow(client: TestClient) -> None:
    """Test complete login with 2FA flow."""
    username, password, headers = _register_and_login(client)

    # Setup and verify 2FA
    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    secret = setup_response.json()["otp_secret"]

    totp = pyotp.TOTP(secret)
    otp_code = totp.now()

    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": otp_code},
        headers=headers,
    )
    assert verify_response.status_code == 200

    # Initial login
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    temp_token = login_response.json()["temp_token"]

    # Get current OTP code
    current_otp = totp.now()

    # Complete 2FA login
    login_2fa_response = client.post(
        "/api/auth/login-with-2fa",
        json={"temp_token": temp_token, "otp_code": current_otp},
    )
    assert login_2fa_response.status_code == 200
    final_data = login_2fa_response.json()
    assert "access_token" in final_data
    assert final_data["token_type"] == "bearer"
    assert final_data["requires_2fa"] is False


def test_login_with_2fa_rejects_invalid_otp(client: TestClient) -> None:
    """Test 2FA login rejects invalid OTP code."""
    username, password, headers = _register_and_login(client)

    # Setup and verify 2FA
    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    secret = setup_response.json()["otp_secret"]

    totp = pyotp.TOTP(secret)
    otp_code = totp.now()

    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": otp_code},
        headers=headers,
    )
    assert verify_response.status_code == 200

    # Initial login
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    temp_token = login_response.json()["temp_token"]

    # Try 2FA login with wrong OTP
    login_2fa_response = client.post(
        "/api/auth/login-with-2fa",
        json={"temp_token": temp_token, "otp_code": "000000"},
    )
    assert login_2fa_response.status_code == 401
    assert "Invalid OTP" in login_2fa_response.json()["detail"]


def test_login_with_2fa_rejects_invalid_token(client: TestClient) -> None:
    """Test 2FA login rejects invalid temp token."""
    login_2fa_response = client.post(
        "/api/auth/login-with-2fa",
        json={"temp_token": "invalid_token_12345", "otp_code": "123456"},
    )
    assert login_2fa_response.status_code == 401
    assert "Invalid or expired" in login_2fa_response.json()["detail"]


def test_login_without_2fa_still_works(client: TestClient) -> None:
    """Test that users without 2FA can still login normally."""
    username, password, _ = _register_and_login(client)

    # Login without 2FA setup
    login_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert login_response.status_code == 200
    login_data = login_response.json()
    assert login_data["requires_2fa"] is False
    assert "access_token" in login_data


def test_oauth2_token_login_returns_bearer_token(client: TestClient) -> None:
    username, password, _ = _register_and_login(client)

    token_response = client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_response.status_code == 200
    data = token_response.json()
    assert "access_token" in data
    assert data["token_type"] == "bearer"


def test_oauth2_token_login_allows_2fa_enabled_account(client: TestClient) -> None:
    username, password, headers = _register_and_login(client)

    setup_response = client.post("/api/auth/setup-2fa", headers=headers)
    secret = setup_response.json()["otp_secret"]
    otp_code = pyotp.TOTP(secret).now()
    verify_response = client.post(
        "/api/auth/verify-2fa",
        json={"otp_secret": secret, "otp_code": otp_code},
        headers=headers,
    )
    assert verify_response.status_code == 200

    token_response = client.post(
        "/api/auth/token",
        data={"username": username, "password": password},
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    assert token_response.status_code == 200
    token_data = token_response.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"


def test_login_lockout_after_failed_attempts(client: TestClient) -> None:
    """User is locked after repeated failed password attempts."""
    username, password, _ = _register_and_login(client)

    for _ in range(4):
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPass123!"},
        )
        assert response.status_code == 401

    fifth_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": "WrongPass123!"},
    )
    assert fifth_response.status_code == 423

    locked_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert locked_response.status_code == 423


def test_successful_login_resets_failed_attempt_counter(client: TestClient) -> None:
    """Successful login clears failed attempt counter for user."""
    username, password, _ = _register_and_login(client)

    for _ in range(2):
        response = client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPass123!"},
        )
        assert response.status_code == 401

    success_response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert success_response.status_code == 200

    with db.get_connection() as connection:
        row = connection.execute(
            "SELECT failed_login_attempts, locked_until FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    assert row is not None
    assert row["failed_login_attempts"] == 0
    assert row["locked_until"] is None


def test_login_unlocks_after_lock_window_expires(client: TestClient) -> None:
    """Locked account can login again after locked_until is in the past."""
    username, password, _ = _register_and_login(client)

    for _ in range(5):
        client.post(
            "/api/auth/login",
            json={"username": username, "password": "WrongPass123!"},
        )

    with db.get_connection() as connection:
        expired_lock = (
            dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        connection.execute(
            "UPDATE users SET locked_until = ? WHERE username = ?",
            (expired_lock, username),
        )
        connection.commit()

    response = client.post(
        "/api/auth/login",
        json={"username": username, "password": password},
    )
    assert response.status_code == 200
