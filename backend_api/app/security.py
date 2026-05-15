from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from typing import Any

import pyotp
import qrcode
from io import BytesIO

SECRET_KEY = os.environ.get("SECUREDROP_SECRET_KEY", "dev-secret-change-me")
ACCESS_TOKEN_TTL_SECONDS = int(os.environ.get(
    "SECUREDROP_ACCESS_TOKEN_TTL", "900"))
PASSWORD_ITERATIONS = 210000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def hash_password(password: str, salt: bytes | None = None) -> tuple[str, str]:
    salt_bytes = salt or secrets.token_bytes(16)
    password_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PASSWORD_ITERATIONS,
    )
    return _b64url_encode(salt_bytes), _b64url_encode(password_hash)


def verify_password(password: str, password_salt: str, password_hash: str) -> bool:
    salt_bytes = _b64url_decode(password_salt)
    expected_hash = _b64url_decode(password_hash)
    actual_hash = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt_bytes,
        PASSWORD_ITERATIONS,
    )
    return hmac.compare_digest(actual_hash, expected_hash)


def create_access_token(payload: dict[str, Any], expires_in: int = ACCESS_TOKEN_TTL_SECONDS) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    body = dict(payload)
    body["exp"] = int(time.time()) + expires_in
    header_b64 = _b64url_encode(json.dumps(
        header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(
        body, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    signature = hmac.new(SECRET_KEY.encode("utf-8"),
                         signing_input, hashlib.sha256).digest()
    return f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> dict[str, Any]:
    try:
        header_b64, payload_b64, signature_b64 = token.split(".")
    except ValueError as exc:
        raise ValueError("Invalid token") from exc

    signing_input = f"{header_b64}.{payload_b64}".encode("utf-8")
    expected_signature = hmac.new(
        SECRET_KEY.encode("utf-8"),
        signing_input,
        hashlib.sha256,
    ).digest()
    provided_signature = _b64url_decode(signature_b64)
    if not hmac.compare_digest(expected_signature, provided_signature):
        raise ValueError("Invalid token")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    if exp < int(time.time()):
        raise ValueError("Token expired")
    return payload


def generate_otp_secret() -> str:
    """Generate a random OTP secret for TOTP."""
    return pyotp.random_base32()


def get_totp(otp_secret: str) -> pyotp.TOTP:
    """Create a TOTP object from secret."""
    return pyotp.TOTP(otp_secret)


def get_provisioning_uri(otp_secret: str, username: str, issuer: str = "SecureDrop") -> str:
    """Generate provisioning URI for QR code."""
    totp = get_totp(otp_secret)
    return totp.provisioning_uri(name=username, issuer_name=issuer)


def generate_qr_code_png(provisioning_uri: str) -> bytes:
    """Generate QR code as PNG bytes."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    img_bytes = BytesIO()
    img.save(img_bytes, format="PNG")
    return img_bytes.getvalue()


def verify_otp_code(otp_secret: str, otp_code: str, window: int = 1) -> bool:
    """Verify OTP code with tolerance window."""
    totp = get_totp(otp_secret)
    return totp.verify(otp_code, valid_window=window)
