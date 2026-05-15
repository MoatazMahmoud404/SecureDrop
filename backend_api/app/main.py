from __future__ import annotations

import datetime as dt
import json
import os
import re
import secrets
from pathlib import Path
from typing import Iterator, Literal

from fastapi import Depends, FastAPI, File, HTTPException, Query, Request, UploadFile, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from slowapi.util import get_remote_address

from backend_api.app.audit import log_audit_event
from backend_api.app.db import get_connection, init_db
from backend_api.app.security import (
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
    generate_otp_secret,
    get_provisioning_uri,
    generate_qr_code_png,
    verify_otp_code,
)
from backend_api.app.socket_client import download_file, upload_file

BASE_DIR = Path(__file__).resolve().parents[2]
STORAGE_DIR = BASE_DIR / "storage"
STORAGE_DIR.mkdir(parents=True, exist_ok=True)
MAX_UPLOAD_BYTES = int(os.environ.get(
    "MAX_UPLOAD_BYTES", str(100 * 1024 * 1024)))
ALLOWED_EXTENSIONS = {
    ".txt",
    ".pdf",
    ".doc",
    ".docx",
    ".png",
    ".jpg",
    ".jpeg",
    ".zip",
}

app = FastAPI(title="SecureDrop API", version="0.1.0")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/token")
limiter = Limiter(key_func=get_remote_address)

MAX_FAILED_LOGIN_ATTEMPTS = int(
    os.environ.get("MAX_FAILED_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.environ.get("LOGIN_LOCKOUT_MINUTES", "15"))
LOGIN_RATE_LIMIT = os.environ.get("LOGIN_RATE_LIMIT", "20/minute")
REGISTER_RATE_LIMIT = os.environ.get("REGISTER_RATE_LIMIT", "10/hour")
LOGIN_2FA_RATE_LIMIT = os.environ.get("LOGIN_2FA_RATE_LIMIT", "20/minute")
REFRESH_TOKEN_TTL_SECONDS = int(
    os.environ.get("SECUREDROP_REFRESH_TOKEN_TTL", str(7 * 24 * 60 * 60))
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RegisterRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    username: str
    password: str


class TransferRequest(BaseModel):
    file_name: str = Field(min_length=1, max_length=255)
    file_size: int = Field(gt=0)


class UpdateFileRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class TokenResponse(BaseModel):
    socket_host: str
    socket_port: int
    token: str
    expires_at: str


class FileRecord(BaseModel):
    id: str
    name: str
    size: int
    checksum_sha256: str | None = None
    owner: str
    uploaded_at: str


class AuditLogRecord(BaseModel):
    id: str
    action: str
    resource_type: str | None = None
    resource_id: str | None = None
    status: str
    ip_address: str | None = None
    user_agent: str | None = None
    timestamp: str
    details: dict | None = None


class AdminAuditLogRecord(AuditLogRecord):
    user_id: str | None = None
    username: str | None = None


class LoginResponse(BaseModel):
    access_token: str | None = None
    token_type: str | None = None
    requires_2fa: bool = False
    temp_token: str | None = None  # Temporary token for 2FA verification
    refresh_token: str | None = None


class RefreshTokenRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class LogoutRequest(BaseModel):
    refresh_token: str = Field(min_length=16)


class ShareLinkCreateRequest(BaseModel):
    expires_in_minutes: int = Field(default=60, ge=1, le=10080)
    max_downloads: int = Field(default=-1, ge=-1, le=1000)
    password: str | None = Field(default=None, min_length=4, max_length=128)


class ShareLinkResponse(BaseModel):
    token: str
    share_path: str
    expires_at: str
    requires_password: bool
    max_downloads: int


class ShareLinkMetadataResponse(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    expires_at: str
    requires_password: bool
    remaining_downloads: int


class ShareLinkDownloadRequest(BaseModel):
    password: str | None = Field(default=None, max_length=128)


class UserSummary(BaseModel):
    id: str
    username: str
    role: str
    is_active: bool = True


class AdminUserSummary(UserSummary):
    created_at: str


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["user", "admin"] = "user"


class AdminUpdateUserRequest(BaseModel):
    is_active: bool | None = None
    role: Literal["user", "admin"] | None = None


class ShareWithUserRequest(BaseModel):
    recipient_username: str = Field(min_length=3, max_length=64)
    permission: Literal["view", "download"] = "download"
    password: str | None = Field(default=None, min_length=4, max_length=128)


class ShareWithUsersRequest(BaseModel):
    recipient_usernames: list[str] = Field(default_factory=list)
    share_with_all_users: bool = False
    permission: Literal["view", "download"] = "download"
    password: str | None = Field(default=None, min_length=4, max_length=128)


class SharedFileRecord(BaseModel):
    file_id: str
    file_name: str
    file_size: int
    owner_username: str
    permission: Literal["view", "download"]
    requires_password: bool = False
    shared_at: str


class OTPSetupResponse(BaseModel):
    otp_secret: str
    qr_code_data_url: str


class OTPVerifyRequest(BaseModel):
    otp_secret: str = Field(min_length=26)  # Base32 encoded
    otp_code: str = Field(min_length=6, max_length=6)


class Disable2FARequest(BaseModel):
    otp_code: str = Field(min_length=6, max_length=6)


class TwoFAStatusResponse(BaseModel):
    enabled: bool


class LoginWith2FARequest(BaseModel):
    temp_token: str = Field(min_length=1)  # Token from initial login
    otp_code: str = Field(min_length=6, max_length=6)


def _get_pending_transfer(token: str):
    with get_connection() as connection:
        return connection.execute(
            """
            SELECT token, user_id, action, file_id, file_name, file_size, status
            FROM pending_transfers
            WHERE token = ?
            """,
            (token,),
        ).fetchone()


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _pending_transfer_expiry_iso() -> str:
    ttl_seconds = int(os.environ.get("SECUREDROP_TRANSFER_TOKEN_TTL", "600"))
    return (
        dt.datetime.now(dt.UTC) + dt.timedelta(seconds=ttl_seconds)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _prime_stream_for_response(stream: Iterator[bytes]) -> Iterator[bytes]:
    iterator = iter(stream)
    first_chunk: bytes | None = None
    try:
        first_chunk = next(iterator)
    except StopIteration:
        first_chunk = None

    def _wrapped() -> Iterator[bytes]:
        if first_chunk is not None:
            yield first_chunk
        yield from iterator

    return _wrapped()


def _issue_token() -> str:
    return secrets.token_urlsafe(32)


def _parse_iso(value: str | None) -> dt.datetime | None:
    if not value:
        return None
    try:
        return dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _lock_until_iso() -> str:
    return (
        dt.datetime.now(dt.UTC) + dt.timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _share_link_is_expired(expires_at: str) -> bool:
    parsed = _parse_iso(expires_at)
    if parsed is None:
        return True
    return parsed <= dt.datetime.now(dt.UTC)


def _sanitize_name(file_name: str) -> str:
    cleaned = Path(file_name).name.strip()
    if not cleaned or cleaned in {".", ".."}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid file name")
    if any(ch in cleaned for ch in ("\n", "\r", "\t")):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid file name",
        )
    # Compatibility guard for older socket servers that parse commands by spaces.
    return re.sub(r"\s+", "_", cleaned)


def _normalize_share_permission(permission: str) -> str:
    normalized = permission.strip().lower()
    if normalized not in {"view", "download"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="permission must be either 'view' or 'download'",
        )
    return normalized


def _validate_upload_constraints(file_name: str, file_size: int) -> None:
    extension = Path(file_name).suffix.lower()
    if extension not in ALLOWED_EXTENSIONS:
        allowed = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type. Allowed: {allowed}",
        )

    if file_size <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file is not allowed")

    if file_size > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"File exceeds max size of {MAX_UPLOAD_BYTES} bytes",
        )


def _create_user_token(user_id: str, username: str, role: str) -> str:
    return create_access_token({"sub": user_id, "username": username, "role": role})


def _issue_refresh_token(user_id: str) -> str:
    refresh_token = create_access_token(
        {
            "sub": user_id,
            "type": "refresh",
            "jti": _issue_token(),
        },
        expires_in=REFRESH_TOKEN_TTL_SECONDS,
    )
    expires_at = (
        dt.datetime.now(dt.UTC) +
        dt.timedelta(seconds=REFRESH_TOKEN_TTL_SECONDS)
    ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO refresh_tokens (token, user_id, issued_at, expires_at, revoked)
            VALUES (?, ?, ?, ?, FALSE)
            """,
            (refresh_token, user_id, _now_iso(), expires_at),
        )
        connection.commit()

    return refresh_token


def _issue_auth_tokens(user_id: str, username: str, role: str) -> tuple[str, str]:
    access_token = _create_user_token(user_id, username, role)
    refresh_token = _issue_refresh_token(user_id)
    return access_token, refresh_token


def _get_current_user(token: str = Depends(oauth2_scheme)) -> dict[str, str]:
    try:
        payload = decode_access_token(token)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, role, is_active FROM users WHERE id = ?",
            (payload.get("sub"),),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid user")

    if not bool(row["is_active"]):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is inactive",
        )

    return {"id": row["id"], "username": row["username"], "role": row["role"]}


def _require_roles(required_roles: set[str]):
    def _role_guard(current_user: dict[str, str] = Depends(_get_current_user)) -> dict[str, str]:
        if current_user.get("role") not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        return current_user

    return _role_guard


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/auth/register")
@limiter.limit(REGISTER_RATE_LIMIT)
def register(request: Request, payload: RegisterRequest) -> dict[str, str]:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
        if existing is not None:
            log_audit_event(
                action="register",
                status="failed",
                request=request,
                details={"reason": "username_exists",
                         "username": payload.username},
            )
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="Username already exists")

        user_id = secrets.token_urlsafe(16)
        password_salt, password_hash = hash_password(payload.password)
        connection.execute(
            "INSERT INTO users (id, username, password_salt, password_hash, created_at, role) VALUES (?, ?, ?, ?, ?, 'user')",
            (user_id, payload.username, password_salt, password_hash, _now_iso()),
        )
        connection.commit()
    log_audit_event(
        action="register",
        status="success",
        request=request,
        user_id=user_id,
        resource_type="user",
        resource_id=user_id,
        details={"username": payload.username},
    )
    return {"message": "registered"}


@app.post("/api/auth/login")
@limiter.limit(LOGIN_RATE_LIMIT)
def login(request: Request, payload: LoginRequest) -> LoginResponse:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, role, is_active, password_salt, password_hash, otp_enabled, failed_login_attempts, locked_until FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()

        if row is not None and not bool(row["is_active"]):
            log_audit_event(
                action="login",
                status="failed",
                request=request,
                user_id=row["id"],
                resource_type="user",
                resource_id=row["id"],
                details={"reason": "inactive_user"},
            )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )

        if row is not None:
            locked_until = _parse_iso(row["locked_until"])
            if locked_until is not None and locked_until > dt.datetime.now(dt.UTC):
                log_audit_event(
                    action="login",
                    status="failed",
                    request=request,
                    user_id=row["id"],
                    resource_type="user",
                    resource_id=row["id"],
                    details={"reason": "account_locked"},
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Account temporarily locked. Try again later.",
                )

        if row is None or not verify_password(payload.password, row["password_salt"], row["password_hash"]):
            if row is not None:
                failed_attempts = int(row["failed_login_attempts"] or 0) + 1
                lock_until: str | None = None

                if failed_attempts >= MAX_FAILED_LOGIN_ATTEMPTS:
                    failed_attempts = 0
                    lock_until = _lock_until_iso()

                connection.execute(
                    "UPDATE users SET failed_login_attempts = ?, locked_until = ? WHERE id = ?",
                    (failed_attempts, lock_until, row["id"]),
                )
                connection.commit()

                if lock_until is not None:
                    log_audit_event(
                        action="login",
                        status="failed",
                        request=request,
                        user_id=row["id"],
                        resource_type="user",
                        resource_id=row["id"],
                        details={"reason": "lockout_triggered"},
                    )
                    raise HTTPException(
                        status_code=status.HTTP_423_LOCKED,
                        detail="Account temporarily locked. Try again later.",
                    )

            log_audit_event(
                action="login",
                status="failed",
                request=request,
                user_id=row["id"] if row is not None else None,
                details={"reason": "invalid_credentials",
                         "username": payload.username},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

        if (row["failed_login_attempts"] or 0) > 0 or row["locked_until"] is not None:
            connection.execute(
                "UPDATE users SET failed_login_attempts = 0, locked_until = NULL WHERE id = ?",
                (row["id"],),
            )
            connection.commit()

    # Check if 2FA is enabled for this user
    if row["otp_enabled"]:
        # Generate a temporary token for 2FA verification
        temp_token = _issue_token()
        with get_connection() as connection:
            connection.execute(
                "INSERT INTO pending_transfers (token, user_id, action, status, created_at, expires_at) VALUES (?, ?, 'login_2fa', 'pending', ?, ?)",
                (temp_token, row["id"], _now_iso(),
                 _pending_transfer_expiry_iso()),
            )
            connection.commit()
        log_audit_event(
            action="login_challenge",
            status="success",
            request=request,
            user_id=row["id"],
            resource_type="user",
            resource_id=row["id"],
            details={"requires_2fa": True},
        )
        return LoginResponse(requires_2fa=True, temp_token=temp_token)

    # No 2FA, return access + refresh tokens
    token, refresh_token = _issue_auth_tokens(
        row["id"], row["username"], row["role"])
    log_audit_event(
        action="login",
        status="success",
        request=request,
        user_id=row["id"],
        resource_type="user",
        resource_id=row["id"],
    )
    return LoginResponse(
        access_token=token,
        refresh_token=refresh_token,
        token_type="bearer",
        requires_2fa=False,
    )


@app.post("/api/auth/token")
@limiter.limit(LOGIN_RATE_LIMIT)
def token_login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()) -> dict[str, str]:
    login_response = login(
        request,
        LoginRequest(username=form_data.username, password=form_data.password),
    )

    if login_response.requires_2fa:
        # Allow Swagger Authorize username/password flow for 2FA-enabled accounts.
        # The password has already been validated by login().
        with get_connection() as connection:
            user = connection.execute(
                "SELECT id, username, role, is_active FROM users WHERE username = ?",
                (form_data.username,),
            ).fetchone()
            if user is None:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid credentials",
                )
            if not bool(user["is_active"]):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="User account is inactive",
                )

            if login_response.temp_token:
                connection.execute(
                    "UPDATE pending_transfers SET status = 'consumed' WHERE token = ?",
                    (login_response.temp_token,),
                )
                connection.commit()

        access_token = _create_user_token(
            user["id"], user["username"], user["role"])
        log_audit_event(
            action="token_login",
            status="success",
            request=request,
            user_id=user["id"],
            resource_type="user",
            resource_id=user["id"],
            details={"bypassed_2fa": True},
        )
        return {
            "access_token": access_token,
            "token_type": "bearer",
        }

    if not login_response.access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )

    return {
        "access_token": login_response.access_token,
        "token_type": "bearer",
    }


@app.post("/api/auth/setup-2fa")
def setup_2fa(request: Request, current_user: dict[str, str] = Depends(_get_current_user)) -> OTPSetupResponse:
    """Generate OTP secret and QR code for 2FA setup."""
    otp_secret = generate_otp_secret()
    provisioning_uri = get_provisioning_uri(
        otp_secret, current_user["username"])
    qr_code_png = generate_qr_code_png(provisioning_uri)

    # Convert PNG to base64 data URL
    import base64
    qr_code_data_url = f"data:image/png;base64,{base64.b64encode(qr_code_png).decode()}"

    log_audit_event(
        action="setup_2fa",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=current_user["id"],
    )

    return OTPSetupResponse(
        otp_secret=otp_secret,
        qr_code_data_url=qr_code_data_url
    )


@app.get("/api/auth/2fa-status", response_model=TwoFAStatusResponse)
def get_2fa_status(current_user: dict[str, str] = Depends(_get_current_user)) -> TwoFAStatusResponse:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT otp_enabled FROM users WHERE id = ?",
            (current_user["id"],),
        ).fetchone()

    return TwoFAStatusResponse(enabled=bool(row["otp_enabled"]) if row is not None else False)


@app.post("/api/auth/verify-2fa")
def verify_2fa(request: Request, payload: OTPVerifyRequest, current_user: dict[str, str] = Depends(_get_current_user)) -> dict[str, str]:
    """Verify OTP code and enable 2FA for user."""
    # Verify the OTP code against the provided secret
    if not verify_otp_code(payload.otp_secret, payload.otp_code):
        log_audit_event(
            action="verify_2fa",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="user",
            resource_id=current_user["id"],
            details={"reason": "invalid_otp"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP code")

    # Save the OTP secret and enable 2FA for the user
    with get_connection() as connection:
        connection.execute(
            "UPDATE users SET otp_secret = ?, otp_enabled = 1 WHERE id = ?",
            (payload.otp_secret, current_user["id"]),
        )
        connection.commit()

    log_audit_event(
        action="verify_2fa",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=current_user["id"],
    )

    return {"status": "success", "message": "2FA enabled successfully"}


@app.post("/api/auth/disable-2fa")
def disable_2fa(
    request: Request,
    payload: Disable2FARequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> dict[str, str]:
    with get_connection() as connection:
        user = connection.execute(
            "SELECT otp_enabled, otp_secret FROM users WHERE id = ?",
            (current_user["id"],),
        ).fetchone()

        if user is None or not user["otp_enabled"] or not user["otp_secret"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="2FA is not enabled",
            )

        if not verify_otp_code(user["otp_secret"], payload.otp_code):
            log_audit_event(
                action="disable_2fa",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="user",
                resource_id=current_user["id"],
                details={"reason": "invalid_otp"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid OTP code",
            )

        connection.execute(
            "UPDATE users SET otp_secret = NULL, otp_enabled = 0 WHERE id = ?",
            (current_user["id"],),
        )
        connection.commit()

    log_audit_event(
        action="disable_2fa",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=current_user["id"],
    )

    return {"status": "success", "message": "2FA disabled successfully"}


@app.post("/api/auth/login-with-2fa")
@limiter.limit(LOGIN_2FA_RATE_LIMIT)
def login_with_2fa(request: Request, payload: LoginWith2FARequest) -> LoginResponse:
    """Complete login with 2FA OTP verification."""
    # Get pending transfer with temp token
    with get_connection() as connection:
        pending = connection.execute(
            "SELECT token, user_id FROM pending_transfers WHERE token = ? AND action = 'login_2fa' AND status = 'pending'",
            (payload.temp_token,),
        ).fetchone()

        if not pending:
            log_audit_event(
                action="login_with_2fa",
                status="failed",
                request=request,
                details={"reason": "invalid_temp_token"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired 2FA token")

        # Get user and their OTP secret
        user = connection.execute(
            "SELECT id, username, role, otp_secret FROM users WHERE id = ?",
            (pending["user_id"],),
        ).fetchone()

    if not user or not user["otp_secret"]:
        log_audit_event(
            action="login_with_2fa",
            status="failed",
            request=request,
            user_id=user["id"] if user is not None else None,
            details={"reason": "2fa_not_configured"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="2FA not properly configured")

    # Verify OTP code
    if not verify_otp_code(user["otp_secret"], payload.otp_code):
        log_audit_event(
            action="login_with_2fa",
            status="failed",
            request=request,
            user_id=user["id"],
            details={"reason": "invalid_otp"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid OTP code")

    # Mark pending transfer as complete
    with get_connection() as connection:
        connection.execute(
            "UPDATE pending_transfers SET status = 'completed' WHERE token = ?",
            (payload.temp_token,),
        )
        connection.commit()

    # Return access + refresh tokens
    token, refresh_token = _issue_auth_tokens(
        user["id"], user["username"], user["role"])
    log_audit_event(
        action="login_with_2fa",
        status="success",
        request=request,
        user_id=user["id"],
        resource_type="user",
        resource_id=user["id"],
    )
    return LoginResponse(
        access_token=token,
        refresh_token=refresh_token,
        token_type="bearer",
        requires_2fa=False,
    )


@app.post("/api/auth/refresh", response_model=LoginResponse)
def refresh_access_token(request: Request, payload: RefreshTokenRequest) -> LoginResponse:
    try:
        refresh_payload = decode_access_token(payload.refresh_token)
    except ValueError as exc:
        log_audit_event(
            action="refresh_token",
            status="failed",
            request=request,
            details={"reason": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        ) from exc

    if refresh_payload.get("type") != "refresh":
        log_audit_event(
            action="refresh_token",
            status="failed",
            request=request,
            user_id=refresh_payload.get("sub"),
            details={"reason": "invalid_token_type"},
        )
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    user_id = refresh_payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token",
        )

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT token, user_id, revoked, expires_at
            FROM refresh_tokens
            WHERE token = ? AND user_id = ?
            """,
            (payload.refresh_token, user_id),
        ).fetchone()

        if row is None or bool(row["revoked"]):
            log_audit_event(
                action="refresh_token",
                status="failed",
                request=request,
                user_id=user_id,
                details={"reason": "not_found_or_revoked"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )

        expires_at = _parse_iso(row["expires_at"])
        if expires_at is not None and expires_at <= dt.datetime.now(dt.UTC):
            connection.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE token = ?",
                (payload.refresh_token,),
            )
            connection.commit()
            log_audit_event(
                action="refresh_token",
                status="failed",
                request=request,
                user_id=user_id,
                details={"reason": "expired"},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh token expired",
            )

        user = connection.execute(
            "SELECT id, username, role, is_active FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid refresh token",
            )
        if not bool(user["is_active"]):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="User account is inactive",
            )

        connection.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token = ?",
            (payload.refresh_token,),
        )
        connection.commit()

    access_token, new_refresh_token = _issue_auth_tokens(
        user["id"], user["username"], user["role"])
    log_audit_event(
        action="refresh_token",
        status="success",
        request=request,
        user_id=user["id"],
        resource_type="user",
        resource_id=user["id"],
    )
    return LoginResponse(
        access_token=access_token,
        refresh_token=new_refresh_token,
        token_type="bearer",
        requires_2fa=False,
    )


@app.post("/api/auth/logout")
def logout(request: Request, payload: LogoutRequest) -> dict[str, str]:
    user_id: str | None = None
    try:
        decoded = decode_access_token(payload.refresh_token)
        user_id = decoded.get("sub")
    except ValueError:
        user_id = None

    with get_connection() as connection:
        connection.execute(
            "UPDATE refresh_tokens SET revoked = TRUE WHERE token = ?",
            (payload.refresh_token,),
        )
        connection.commit()
    log_audit_event(
        action="logout",
        status="success",
        request=request,
        user_id=user_id,
        resource_type="user",
        resource_id=user_id,
    )
    return {"message": "logged out"}


@app.get("/api/files", response_model=list[FileRecord])
def list_files(current_user: dict[str, str] = Depends(_get_current_user)) -> list[FileRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT files.id, files.name, files.size, files.uploaded_at, users.username AS owner
                  , files.checksum_sha256
            FROM files
            JOIN users ON users.id = files.owner_id
            WHERE files.owner_id = ?
            ORDER BY files.uploaded_at DESC
            """,
            (current_user["id"],),
        ).fetchall()

    return [
        FileRecord(
            id=row["id"],
            name=row["name"],
            size=row["size"],
            checksum_sha256=row["checksum_sha256"],
            owner=row["owner"],
            uploaded_at=row["uploaded_at"],
        )
        for row in rows
    ]


@app.get("/api/users", response_model=list[UserSummary])
def list_users(current_user: dict[str, str] = Depends(_get_current_user)) -> list[UserSummary]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, username, role, is_active
            FROM users
            WHERE id != ? AND is_active = 1
            ORDER BY username ASC
            """,
            (current_user["id"],),
        ).fetchall()

    return [
        UserSummary(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
        )
        for row in rows
    ]


@app.get("/api/admin/users", response_model=list[AdminUserSummary])
def list_admin_users(
    current_user: dict[str, str] = Depends(_require_roles({"admin"})),
) -> list[AdminUserSummary]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, username, role, is_active, created_at
            FROM users
            ORDER BY username ASC
            """,
        ).fetchall()

    return [
        AdminUserSummary(
            id=row["id"],
            username=row["username"],
            role=row["role"],
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
        )
        for row in rows
    ]


@app.post("/api/admin/users", response_model=AdminUserSummary)
def create_admin_user(
    request: Request,
    payload: AdminCreateUserRequest,
    current_user: dict[str, str] = Depends(_require_roles({"admin"})),
) -> AdminUserSummary:
    with get_connection() as connection:
        existing = connection.execute(
            "SELECT id FROM users WHERE username = ?",
            (payload.username,),
        ).fetchone()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Username already exists",
            )

        user_id = secrets.token_urlsafe(16)
        password_salt, password_hash = hash_password(payload.password)
        created_at = _now_iso()
        connection.execute(
            """
            INSERT INTO users (id, username, password_salt, password_hash, created_at, role, is_active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
            """,
            (user_id, payload.username, password_salt,
             password_hash, created_at, payload.role),
        )
        connection.commit()

    log_audit_event(
        action="admin_create_user",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=user_id,
        details={"username": payload.username, "role": payload.role},
    )

    return AdminUserSummary(
        id=user_id,
        username=payload.username,
        role=payload.role,
        is_active=True,
        created_at=created_at,
    )


@app.patch("/api/admin/users/{user_id}", response_model=AdminUserSummary)
def update_admin_user(
    request: Request,
    user_id: str,
    payload: AdminUpdateUserRequest,
    current_user: dict[str, str] = Depends(_require_roles({"admin"})),
) -> AdminUserSummary:
    if payload.is_active is None and payload.role is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No update fields provided",
        )

    if user_id == current_user["id"] and payload.is_active is False:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot deactivate your own account",
        )

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username, role, is_active, created_at FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        next_role = payload.role if payload.role is not None else row["role"]
        next_is_active = bool(
            payload.is_active) if payload.is_active is not None else bool(row["is_active"])

        connection.execute(
            "UPDATE users SET role = ?, is_active = ? WHERE id = ?",
            (next_role, int(next_is_active), user_id),
        )
        if not next_is_active:
            connection.execute(
                "UPDATE refresh_tokens SET revoked = TRUE WHERE user_id = ?",
                (user_id,),
            )
        connection.commit()

    log_audit_event(
        action="admin_update_user",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=user_id,
        details={"role": next_role, "is_active": next_is_active},
    )

    return AdminUserSummary(
        id=row["id"],
        username=row["username"],
        role=next_role,
        is_active=next_is_active,
        created_at=row["created_at"],
    )


@app.delete("/api/admin/users/{user_id}")
def delete_admin_user(
    request: Request,
    user_id: str,
    current_user: dict[str, str] = Depends(_require_roles({"admin"})),
) -> dict[str, str]:
    if user_id == current_user["id"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="You cannot delete your own account",
        )

    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, username FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found",
            )

        owned_files = connection.execute(
            "SELECT COUNT(1) AS total FROM files WHERE owner_id = ?",
            (user_id,),
        ).fetchone()
        if owned_files is not None and int(owned_files["total"] or 0) > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot delete user that still owns files",
            )

        connection.execute(
            "DELETE FROM file_shares WHERE recipient_id = ?", (user_id,))
        connection.execute(
            "DELETE FROM refresh_tokens WHERE user_id = ?", (user_id,))
        connection.execute(
            "DELETE FROM pending_transfers WHERE user_id = ?", (user_id,))
        connection.execute("DELETE FROM users WHERE id = ?", (user_id,))
        connection.commit()

    log_audit_event(
        action="admin_delete_user",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="user",
        resource_id=user_id,
        details={"username": row["username"]},
    )

    return {"message": "user deleted"}


@app.post("/api/files/{file_id}/share-user")
def share_file_with_user(
    request: Request,
    file_id: str,
    payload: ShareWithUserRequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> dict[str, str]:
    permission = _normalize_share_permission(payload.permission)
    share_password = (payload.password or "").strip() or None
    password_salt: str | None = None
    password_hash_value: str | None = None
    if share_password:
        password_salt, password_hash_value = hash_password(share_password)

    with get_connection() as connection:
        file_row = connection.execute(
            "SELECT id, name FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        ).fetchone()
        if file_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        recipient = connection.execute(
            "SELECT id, username FROM users WHERE username = ?",
            (payload.recipient_username,),
        ).fetchone()
        if recipient is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Recipient user not found",
            )
        if recipient["id"] == current_user["id"]:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot share a file with yourself",
            )

        existing_share = connection.execute(
            "SELECT id FROM file_shares WHERE file_id = ? AND recipient_id = ?",
            (file_id, recipient["id"]),
        ).fetchone()
        if existing_share is None:
            connection.execute(
                """
                INSERT INTO file_shares (id, file_id, owner_id, recipient_id, permission, password_salt, password_hash, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    secrets.token_urlsafe(16),
                    file_id,
                    current_user["id"],
                    recipient["id"],
                    permission,
                    password_salt,
                    password_hash_value,
                    _now_iso(),
                ),
            )
        else:
            connection.execute(
                "UPDATE file_shares SET permission = ?, password_salt = ?, password_hash = ? WHERE id = ?",
                (permission, password_salt,
                 password_hash_value, existing_share["id"]),
            )
        connection.commit()

    log_audit_event(
        action="share_file_with_user",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
        details={
            "recipient_username": payload.recipient_username,
            "permission": permission,
            "requires_password": bool(share_password),
        },
    )
    return {"message": "file shared"}


@app.post("/api/files/{file_id}/share-users")
def share_file_with_users(
    request: Request,
    file_id: str,
    payload: ShareWithUsersRequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> dict[str, object]:
    permission = _normalize_share_permission(payload.permission)
    share_password = (payload.password or "").strip() or None
    password_salt: str | None = None
    password_hash_value: str | None = None
    if share_password:
        password_salt, password_hash_value = hash_password(share_password)

    cleaned_usernames = [name.strip()
                         for name in payload.recipient_usernames if name.strip()]
    unique_usernames = list(dict.fromkeys(cleaned_usernames))

    if not payload.share_with_all_users and not unique_usernames:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Provide recipient_usernames or enable share_with_all_users",
        )

    with get_connection() as connection:
        file_row = connection.execute(
            "SELECT id, name FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        ).fetchone()
        if file_row is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        recipient_rows: list = []
        missing_usernames: list[str] = []

        if payload.share_with_all_users:
            recipient_rows = connection.execute(
                "SELECT id, username FROM users WHERE id != ? ORDER BY username ASC",
                (current_user["id"],),
            ).fetchall()
        else:
            placeholders = ",".join("?" for _ in unique_usernames)
            recipient_rows = connection.execute(
                f"SELECT id, username FROM users WHERE username IN ({placeholders})",
                tuple(unique_usernames),
            ).fetchall()
            found_usernames = {row["username"] for row in recipient_rows}
            missing_usernames = [
                username for username in unique_usernames if username not in found_usernames]

        existing_rows = connection.execute(
            "SELECT id, recipient_id FROM file_shares WHERE file_id = ?",
            (file_id,),
        ).fetchall()
        existing_by_recipient_id = {
            row["recipient_id"]: row["id"] for row in existing_rows}

        created_count = 0
        updated_count = 0
        for recipient in recipient_rows:
            if recipient["id"] == current_user["id"]:
                continue

            existing_share_id = existing_by_recipient_id.get(recipient["id"])
            if existing_share_id is None:
                connection.execute(
                    """
                    INSERT INTO file_shares (id, file_id, owner_id, recipient_id, permission, password_salt, password_hash, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        secrets.token_urlsafe(16),
                        file_id,
                        current_user["id"],
                        recipient["id"],
                        permission,
                        password_salt,
                        password_hash_value,
                        _now_iso(),
                    ),
                )
                created_count += 1
            else:
                connection.execute(
                    "UPDATE file_shares SET permission = ?, password_salt = ?, password_hash = ? WHERE id = ?",
                    (permission, password_salt,
                     password_hash_value, existing_share_id),
                )
                updated_count += 1

        connection.commit()

    log_audit_event(
        action="share_file_with_users",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
        details={
            "permission": permission,
            "share_with_all_users": payload.share_with_all_users,
            "requested_recipients": unique_usernames,
            "created_count": created_count,
            "updated_count": updated_count,
            "missing_usernames": missing_usernames,
            "requires_password": bool(share_password),
        },
    )

    return {
        "message": "file shared",
        "created_count": created_count,
        "updated_count": updated_count,
        "missing_usernames": missing_usernames,
    }


@app.get("/api/shared-files", response_model=list[SharedFileRecord])
def list_shared_files(current_user: dict[str, str] = Depends(_get_current_user)) -> list[SharedFileRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                f.id AS file_id,
                f.name AS file_name,
                f.size AS file_size,
                owner.username AS owner_username,
                fs.permission AS permission,
                fs.password_hash AS password_hash,
                fs.created_at AS shared_at
            FROM file_shares fs
            JOIN files f ON f.id = fs.file_id
            JOIN users owner ON owner.id = fs.owner_id
            WHERE fs.recipient_id = ?
            ORDER BY fs.created_at DESC
            """,
            (current_user["id"],),
        ).fetchall()

    return [
        SharedFileRecord(
            file_id=row["file_id"],
            file_name=row["file_name"],
            file_size=row["file_size"],
            owner_username=row["owner_username"],
            permission=row["permission"],
            requires_password=bool(row["password_hash"]),
            shared_at=row["shared_at"],
        )
        for row in rows
    ]


def _download_shared_file_impl(
    request: Request,
    file_id: str,
    current_user: dict[str, str],
    password: str | None,
) -> StreamingResponse:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                f.id,
                f.name,
                f.checksum_sha256,
                fs.permission,
                fs.owner_id,
                fs.password_salt,
                fs.password_hash
            FROM file_shares fs
            JOIN files f ON f.id = fs.file_id
            WHERE fs.file_id = ? AND fs.recipient_id = ?
            """,
            (file_id, current_user["id"]),
        ).fetchone()

    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared file not found",
        )

    if row["permission"] != "download":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You only have view permission for this file",
        )

    if row["password_hash"]:
        provided_password = (password or "").strip()
        if not provided_password or not verify_password(provided_password, row["password_salt"], row["password_hash"]):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid shared file password",
            )

    transfer_token = _issue_token()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO pending_transfers (token, user_id, action, file_id, file_name, created_at, expires_at, status)
            VALUES (?, ?, 'download', ?, ?, ?, ?, 'pending')
            """,
            (
                transfer_token,
                current_user["id"],
                row["id"],
                row["name"],
                _now_iso(),
                _pending_transfer_expiry_iso(),
            ),
        )
        connection.commit()

    try:
        stream = download_file(
            os.environ.get("SOCKET_HOST", "127.0.0.1"),
            int(os.environ.get("SOCKET_PORT", "9000")),
            transfer_token,
            row["name"],
        )
        stream = _prime_stream_for_response(stream)
    except RuntimeError as exc:
        error_message = str(exc)
        log_audit_event(
            action="shared_file_download",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=file_id,
            details={"reason": "socket_download_error",
                     "message": error_message},
        )
        if "file not found" in error_message.lower():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Shared file is no longer available",
            ) from exc
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        ) from exc

    headers = {"Content-Disposition": f'attachment; filename="{row["name"]}"'}
    if row["checksum_sha256"]:
        headers["X-File-Checksum-SHA256"] = row["checksum_sha256"]

    log_audit_event(
        action="shared_file_download",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
        details={"owner_id": row["owner_id"],
                 "used_password": bool(row["password_hash"])},
    )
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)


@app.get("/api/shared-files/{file_id}/download")
def download_shared_file(
    request: Request,
    file_id: str,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> StreamingResponse:
    return _download_shared_file_impl(request, file_id, current_user, password=None)


@app.post("/api/shared-files/{file_id}/download")
def download_shared_file_with_password(
    request: Request,
    file_id: str,
    payload: ShareLinkDownloadRequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> StreamingResponse:
    return _download_shared_file_impl(request, file_id, current_user, password=payload.password)


@app.get("/api/user/activity", response_model=list[AuditLogRecord])
def user_activity(
    limit: int = Query(default=50, ge=1, le=200),
    current_user: dict[str, str] = Depends(_get_current_user),
) -> list[AuditLogRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT id, action, resource_type, resource_id, status, ip_address, user_agent, timestamp, details
            FROM audit_logs
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (current_user["id"], limit),
        ).fetchall()

    logs: list[AuditLogRecord] = []
    for row in rows:
        parsed_details: dict | None = None
        if row["details"]:
            try:
                parsed_details = json.loads(row["details"])
            except json.JSONDecodeError:
                parsed_details = {"raw": row["details"]}
        logs.append(
            AuditLogRecord(
                id=row["id"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                status=row["status"],
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
                timestamp=row["timestamp"],
                details=parsed_details,
            )
        )
    return logs


@app.get("/api/admin/audit-logs", response_model=list[AdminAuditLogRecord])
def admin_audit_logs(
    limit: int = Query(default=100, ge=1, le=500),
    current_user: dict[str, str] = Depends(_require_roles({"admin"})),
) -> list[AdminAuditLogRecord]:
    with get_connection() as connection:
        rows = connection.execute(
            """
            SELECT
                logs.id,
                logs.user_id,
                users.username,
                logs.action,
                logs.resource_type,
                logs.resource_id,
                logs.status,
                logs.ip_address,
                logs.user_agent,
                logs.timestamp,
                logs.details
            FROM audit_logs logs
            LEFT JOIN users ON users.id = logs.user_id
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    logs: list[AdminAuditLogRecord] = []
    for row in rows:
        parsed_details: dict | None = None
        if row["details"]:
            try:
                parsed_details = json.loads(row["details"])
            except json.JSONDecodeError:
                parsed_details = {"raw": row["details"]}
        logs.append(
            AdminAuditLogRecord(
                id=row["id"],
                user_id=row["user_id"],
                username=row["username"],
                action=row["action"],
                resource_type=row["resource_type"],
                resource_id=row["resource_id"],
                status=row["status"],
                ip_address=row["ip_address"],
                user_agent=row["user_agent"],
                timestamp=row["timestamp"],
                details=parsed_details,
            )
        )

    log_audit_event(
        action="admin_audit_logs",
        status="success",
        user_id=current_user["id"],
        resource_type="audit_log",
        details={"limit": limit},
    )
    return logs


@app.post("/api/files/{file_id}/share", response_model=ShareLinkResponse)
def create_share_link(
    request: Request,
    file_id: str,
    payload: ShareLinkCreateRequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> ShareLinkResponse:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, name, size FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        ).fetchone()

        if row is None:
            log_audit_event(
                action="create_share_link",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=file_id,
                details={"reason": "file_not_found"},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        token = _issue_token()
        expires_at = (
            dt.datetime.now(dt.UTC) +
            dt.timedelta(minutes=payload.expires_in_minutes)
        ).replace(microsecond=0).isoformat().replace("+00:00", "Z")

        password_salt: str | None = None
        password_hash_value: str | None = None
        if payload.password:
            password_salt, password_hash_value = hash_password(
                payload.password)

        connection.execute(
            """
            INSERT INTO shared_links (
                token, file_id, owner_id, password_salt, password_hash,
                expires_at, max_downloads, download_count, created_at, revoked
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?, FALSE)
            """,
            (
                token,
                file_id,
                current_user["id"],
                password_salt,
                password_hash_value,
                expires_at,
                payload.max_downloads,
                _now_iso(),
            ),
        )
        connection.commit()

    log_audit_event(
        action="create_share_link",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
        details={
            "file_name": row["name"],
            "expires_in_minutes": payload.expires_in_minutes,
            "max_downloads": payload.max_downloads,
            "requires_password": bool(payload.password),
        },
    )

    return ShareLinkResponse(
        token=token,
        share_path=f"/api/share/{token}",
        expires_at=expires_at,
        requires_password=bool(payload.password),
        max_downloads=payload.max_downloads,
    )


@app.get("/api/share/{token}", response_model=ShareLinkMetadataResponse)
def get_share_link_metadata(request: Request, token: str) -> ShareLinkMetadataResponse:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                s.token,
                s.file_id,
                s.owner_id,
                s.password_hash,
                s.expires_at,
                s.max_downloads,
                s.download_count,
                s.revoked,
                f.name,
                f.size
            FROM shared_links s
            JOIN files f ON f.id = s.file_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()

    if row is None or bool(row["revoked"]):
        log_audit_event(
            action="share_metadata",
            status="failed",
            request=request,
            details={"reason": "invalid_or_revoked_link"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Share link not found",
        )

    if _share_link_is_expired(row["expires_at"]):
        log_audit_event(
            action="share_metadata",
            status="failed",
            request=request,
            user_id=row["owner_id"],
            resource_type="file",
            resource_id=row["file_id"],
            details={"reason": "share_link_expired"},
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link expired",
        )

    if int(row["max_downloads"]) >= 0 and int(row["download_count"]) >= int(row["max_downloads"]):
        log_audit_event(
            action="share_metadata",
            status="failed",
            request=request,
            user_id=row["owner_id"],
            resource_type="file",
            resource_id=row["file_id"],
            details={"reason": "download_limit_reached"},
        )
        raise HTTPException(
            status_code=status.HTTP_410_GONE,
            detail="Share link download limit reached",
        )

    if int(row["max_downloads"]) < 0:
        remaining_downloads = -1
    else:
        remaining_downloads = int(
            row["max_downloads"]) - int(row["download_count"])

    log_audit_event(
        action="share_metadata",
        status="success",
        request=request,
        user_id=row["owner_id"],
        resource_type="file",
        resource_id=row["file_id"],
        details={"remaining_downloads": remaining_downloads},
    )

    return ShareLinkMetadataResponse(
        file_id=row["file_id"],
        file_name=row["name"],
        file_size=row["size"],
        expires_at=row["expires_at"],
        requires_password=bool(row["password_hash"]),
        remaining_downloads=remaining_downloads,
    )


@app.post("/api/share/{token}/download")
def download_from_share_link(
    request: Request,
    token: str,
    payload: ShareLinkDownloadRequest,
) -> StreamingResponse:
    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT
                s.token,
                s.file_id,
                s.owner_id,
                s.password_salt,
                s.password_hash,
                s.expires_at,
                s.max_downloads,
                s.download_count,
                s.revoked,
                f.name,
                f.checksum_sha256
            FROM shared_links s
            JOIN files f ON f.id = s.file_id
            WHERE s.token = ?
            """,
            (token,),
        ).fetchone()

        if row is None or bool(row["revoked"]):
            log_audit_event(
                action="share_download",
                status="failed",
                request=request,
                details={"reason": "invalid_or_revoked_link"},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Share link not found",
            )

        if _share_link_is_expired(row["expires_at"]):
            log_audit_event(
                action="share_download",
                status="failed",
                request=request,
                user_id=row["owner_id"],
                resource_type="file",
                resource_id=row["file_id"],
                details={"reason": "share_link_expired"},
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Share link expired",
            )

        if int(row["max_downloads"]) >= 0 and int(row["download_count"]) >= int(row["max_downloads"]):
            log_audit_event(
                action="share_download",
                status="failed",
                request=request,
                user_id=row["owner_id"],
                resource_type="file",
                resource_id=row["file_id"],
                details={"reason": "download_limit_reached"},
            )
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail="Share link download limit reached",
            )

        if row["password_hash"]:
            if not payload.password or not verify_password(payload.password, row["password_salt"], row["password_hash"]):
                log_audit_event(
                    action="share_download",
                    status="failed",
                    request=request,
                    user_id=row["owner_id"],
                    resource_type="file",
                    resource_id=row["file_id"],
                    details={"reason": "invalid_share_password"},
                )
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid share password",
                )

        transfer_token = _issue_token()
        connection.execute(
            """
            INSERT INTO pending_transfers (token, user_id, action, file_id, file_name, created_at, expires_at, status)
            VALUES (?, ?, 'download', ?, ?, ?, ?, 'pending')
            """,
            (transfer_token, row["owner_id"], row["file_id"],
             row["name"], _now_iso(), _now_iso()),
        )
        connection.execute(
            "UPDATE shared_links SET download_count = download_count + 1 WHERE token = ?",
            (token,),
        )
        connection.commit()

    try:
        stream = download_file(
            os.environ.get("SOCKET_HOST", "127.0.0.1"),
            int(os.environ.get("SOCKET_PORT", "9000")),
            transfer_token,
            row["name"],
        )
        stream = _prime_stream_for_response(stream)
    except RuntimeError as exc:
        log_audit_event(
            action="share_download",
            status="failed",
            request=request,
            user_id=row["owner_id"],
            resource_type="file",
            resource_id=row["file_id"],
            details={"reason": "socket_download_error", "message": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        ) from exc
    headers = {"Content-Disposition": f'attachment; filename="{row["name"]}"'}
    if row["checksum_sha256"]:
        headers["X-File-Checksum-SHA256"] = row["checksum_sha256"]

    log_audit_event(
        action="share_download",
        status="success",
        request=request,
        user_id=row["owner_id"],
        resource_type="file",
        resource_id=row["file_id"],
    )
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)


@app.post("/api/upload-request", response_model=TokenResponse)
def upload_request(request: Request, payload: TransferRequest, current_user: dict[str, str] = Depends(_get_current_user)) -> TokenResponse:
    token = _issue_token()
    safe_name = _sanitize_name(payload.file_name)
    _validate_upload_constraints(safe_name, payload.file_size)
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO pending_transfers (token, user_id, action, file_name, file_size, created_at, expires_at, status)
            VALUES (?, ?, 'upload', ?, ?, ?, ?, 'pending')
            """,
            (token, current_user["id"], safe_name,
             payload.file_size, _now_iso(), _pending_transfer_expiry_iso()),
        )
        connection.commit()
    log_audit_event(
        action="upload_request",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=safe_name,
        details={"file_size": payload.file_size},
    )
    return TokenResponse(
        socket_host=os.environ.get("SOCKET_HOST", "127.0.0.1"),
        socket_port=int(os.environ.get("SOCKET_PORT", "9000")),
        token=token,
        expires_at=_pending_transfer_expiry_iso(),
    )


@app.get("/api/download-request/{file_id}", response_model=TokenResponse)
def download_request(request: Request, file_id: str, current_user: dict[str, str] = Depends(_get_current_user)) -> TokenResponse:
    with get_connection() as connection:
        match = connection.execute(
            "SELECT id, name FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        ).fetchone()

    if match is None:
        log_audit_event(
            action="download_request",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=file_id,
            details={"reason": "file_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    token = _issue_token()
    with get_connection() as connection:
        connection.execute(
            """
            INSERT INTO pending_transfers (token, user_id, action, file_id, file_name, created_at, expires_at, status)
            VALUES (?, ?, 'download', ?, ?, ?, ?, 'pending')
            """,
            (token, current_user["id"], file_id,
             match["name"], _now_iso(), _pending_transfer_expiry_iso()),
        )
        connection.commit()
    log_audit_event(
        action="download_request",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
    )
    return TokenResponse(
        socket_host=os.environ.get("SOCKET_HOST", "127.0.0.1"),
        socket_port=int(os.environ.get("SOCKET_PORT", "9000")),
        token=token,
        expires_at=_pending_transfer_expiry_iso(),
    )


@app.post("/api/upload-commit")
def upload_commit(
    request: Request,
    file: UploadFile = File(...),
    token: str | None = Query(default=None),
    current_user: dict[str, str] = Depends(_get_current_user),
) -> dict[str, str]:
    safe_name = _sanitize_name(file.filename or "upload.bin")
    file.file.seek(0, os.SEEK_END)
    file_size = file.file.tell()
    file.file.seek(0)
    _validate_upload_constraints(safe_name, file_size)

    transfer_token = token
    if transfer_token is None:
        transfer_token = _issue_token()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_transfers (token, user_id, action, file_name, file_size, created_at, expires_at, status)
                VALUES (?, ?, 'upload', ?, ?, ?, ?, 'pending')
                """,
                (transfer_token, current_user["id"],
                 safe_name, file_size, _now_iso(), _pending_transfer_expiry_iso()),
            )
            connection.commit()
    else:
        transfer = _get_pending_transfer(transfer_token)
        if transfer is None or transfer["user_id"] != current_user["id"] or transfer["action"] != "upload" or transfer["status"] != "pending":
            log_audit_event(
                action="upload_commit",
                status="failed",
                request=request,
                user_id=current_user["id"],
                details={"reason": "invalid_upload_token"},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid upload token")
        if transfer["file_name"] and transfer["file_name"] != safe_name:
            log_audit_event(
                action="upload_commit",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=safe_name,
                details={"reason": "file_name_mismatch"},
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Upload token file name mismatch")
        if transfer["file_size"] and int(transfer["file_size"]) != int(file_size):
            log_audit_event(
                action="upload_commit",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=safe_name,
                details={"reason": "file_size_mismatch"},
            )
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Upload token file size mismatch")

    try:
        upload_file(
            os.environ.get("SOCKET_HOST", "127.0.0.1"),
            int(os.environ.get("SOCKET_PORT", "9000")),
            transfer_token,
            safe_name,
            file.file,
            file_size,
        )
    except RuntimeError as exc:
        log_audit_event(
            action="upload_commit",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=safe_name,
            details={"reason": "socket_upload_error", "message": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Upload failed: {exc}",
        ) from exc
    log_audit_event(
        action="upload_commit",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=safe_name,
        details={"file_size": file_size},
    )
    with get_connection() as connection:
        uploaded_row = connection.execute(
            """
            SELECT id
            FROM files
            WHERE owner_id = ? AND name = ?
            ORDER BY uploaded_at DESC
            LIMIT 1
            """,
            (current_user["id"], safe_name),
        ).fetchone()

    return {
        "message": "uploaded",
        "file_name": safe_name,
        "file_id": uploaded_row["id"] if uploaded_row is not None else None,
    }


@app.get("/api/download-commit/{file_id}")
def download_commit(
    request: Request,
    file_id: str,
    token: str | None = Query(default=None),
    current_user: dict[str, str] = Depends(_get_current_user),
) -> StreamingResponse:
    with get_connection() as connection:
        row = connection.execute(
            "SELECT id, name, checksum_sha256 FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        ).fetchone()

    if row is None:
        log_audit_event(
            action="download_commit",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=file_id,
            details={"reason": "file_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    transfer_token = token
    if transfer_token is None:
        transfer_token = _issue_token()
        with get_connection() as connection:
            connection.execute(
                """
                INSERT INTO pending_transfers (token, user_id, action, file_id, file_name, created_at, expires_at, status)
                VALUES (?, ?, 'download', ?, ?, ?, ?, 'pending')
                """,
                (transfer_token, current_user["id"], file_id,
                 row["name"], _now_iso(), _pending_transfer_expiry_iso()),
            )
            connection.commit()
    else:
        transfer = _get_pending_transfer(transfer_token)
        if transfer is None or transfer["user_id"] != current_user["id"] or transfer["action"] != "download" or transfer["status"] != "pending":
            log_audit_event(
                action="download_commit",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=file_id,
                details={"reason": "invalid_download_token"},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid download token")
        if transfer["file_id"] and transfer["file_id"] != file_id:
            log_audit_event(
                action="download_commit",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=file_id,
                details={"reason": "file_id_mismatch"},
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Download token file mismatch")

    try:
        stream = download_file(
            os.environ.get("SOCKET_HOST", "127.0.0.1"),
            int(os.environ.get("SOCKET_PORT", "9000")),
            transfer_token,
            row["name"],
        )
        stream = _prime_stream_for_response(stream)
    except RuntimeError as exc:
        log_audit_event(
            action="download_commit",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=file_id,
            details={"reason": "socket_download_error", "message": str(exc)},
        )
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Download failed: {exc}",
        ) from exc
    headers = {"Content-Disposition": f'attachment; filename="{row["name"]}"'}
    if row["checksum_sha256"]:
        headers["X-File-Checksum-SHA256"] = row["checksum_sha256"]
    log_audit_event(
        action="download_commit",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
    )
    return StreamingResponse(stream, media_type="application/octet-stream", headers=headers)


@app.delete("/api/files/{file_id}")
def delete_file(request: Request, file_id: str, current_user: dict[str, str] = Depends(_get_current_user)) -> dict[str, str]:
    with get_connection() as connection:
        result = connection.execute(
            "DELETE FROM files WHERE id = ? AND owner_id = ?",
            (file_id, current_user["id"]),
        )
        connection.commit()

    if result.rowcount == 0:
        log_audit_event(
            action="delete_file",
            status="failed",
            request=request,
            user_id=current_user["id"],
            resource_type="file",
            resource_id=file_id,
            details={"reason": "file_not_found"},
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    log_audit_event(
        action="delete_file",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
    )
    return {"message": "deleted"}


@app.patch("/api/files/{file_id}", response_model=FileRecord)
def update_file(
    request: Request,
    file_id: str,
    payload: UpdateFileRequest,
    current_user: dict[str, str] = Depends(_get_current_user),
) -> FileRecord:
    safe_name = _sanitize_name(payload.name)

    with get_connection() as connection:
        row = connection.execute(
            """
            SELECT files.id, files.name, files.size, files.uploaded_at, files.checksum_sha256,
                   users.username AS owner
            FROM files
            JOIN users ON users.id = files.owner_id
            WHERE files.id = ? AND files.owner_id = ?
            """,
            (file_id, current_user["id"]),
        ).fetchone()

        if row is None:
            log_audit_event(
                action="update_file",
                status="failed",
                request=request,
                user_id=current_user["id"],
                resource_type="file",
                resource_id=file_id,
                details={"reason": "file_not_found"},
            )
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="File not found",
            )

        connection.execute(
            "UPDATE files SET name = ? WHERE id = ? AND owner_id = ?",
            (safe_name, file_id, current_user["id"]),
        )
        connection.commit()

    log_audit_event(
        action="update_file",
        status="success",
        request=request,
        user_id=current_user["id"],
        resource_type="file",
        resource_id=file_id,
        details={"old_name": row["name"], "new_name": safe_name},
    )

    return FileRecord(
        id=row["id"],
        name=safe_name,
        size=row["size"],
        checksum_sha256=row["checksum_sha256"],
        owner=row["owner"],
        uploaded_at=row["uploaded_at"],
    )


@app.post("/api/dev/seed-file")
def seed_file(payload: TransferRequest) -> dict[str, str]:
    file_id = _issue_token()
    with get_connection() as connection:
        demo_user = connection.execute(
            "SELECT id FROM users WHERE username = 'demo'",
        ).fetchone()
        if demo_user is None:
            password_salt, password_hash = hash_password("DemoPass123!")
            demo_user_id = secrets.token_urlsafe(16)
            connection.execute(
                "INSERT INTO users (id, username, password_salt, password_hash, created_at) VALUES (?, 'demo', ?, ?, ?)",
                (demo_user_id, password_salt, password_hash, _now_iso()),
            )
        else:
            demo_user_id = demo_user["id"]

        connection.execute(
            "INSERT INTO files (id, owner_id, name, size, checksum_sha256, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
            (file_id, demo_user_id, _sanitize_name(
                payload.file_name), payload.file_size, None, _now_iso()),
        )
        connection.commit()
    return {"id": file_id}
