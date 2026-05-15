from __future__ import annotations

import os
import socket
import ssl
import sqlite3
import threading
import hashlib
from pathlib import Path
import secrets
import datetime as dt

BASE_DIR = Path(__file__).resolve().parents[1]
STORAGE_DIR = BASE_DIR / "storage"
CERT_FILE = BASE_DIR / "certs" / "cert.pem"
KEY_FILE = BASE_DIR / "certs" / "key.pem"
DB_PATH = BASE_DIR / "data" / "securedrop.db"
HOST = os.environ.get("SOCKET_HOST", "0.0.0.0")
PORT = int(os.environ.get("SOCKET_PORT", "9000"))
CHUNK_SIZE = 32 * 1024
DB_LOCK = threading.Lock()


def _now_iso() -> str:
    return dt.datetime.now(dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _recv_line(connection: ssl.SSLSocket) -> str:
    data = bytearray()
    while True:
        chunk = connection.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if data.endswith(b"\n"):
            break
    return data.decode("utf-8", errors="replace").strip()


def _safe_name(file_name: str) -> str:
    return Path(file_name).name


def _parse_upload_command(line: str) -> tuple[str, str, int]:
    # Command format: UPLOAD <token> <file_name possibly with spaces> <file_size>
    if not line.upper().startswith("UPLOAD "):
        raise ValueError("invalid command")

    payload = line[len("UPLOAD "):]
    first_space = payload.find(" ")
    if first_space <= 0:
        raise ValueError("missing token")

    token = payload[:first_space]
    file_and_size = payload[first_space + 1:].strip()
    last_space = file_and_size.rfind(" ")
    if last_space <= 0:
        raise ValueError("missing file size")

    file_name = file_and_size[:last_space].strip()
    file_size_str = file_and_size[last_space + 1:].strip()
    if not file_name:
        raise ValueError("missing file name")

    return token, file_name, int(file_size_str)


def _parse_download_command(line: str) -> tuple[str, str]:
    # Command format: DOWNLOAD <token> <file_name possibly with spaces>
    if not line.upper().startswith("DOWNLOAD "):
        raise ValueError("invalid command")

    payload = line[len("DOWNLOAD "):]
    first_space = payload.find(" ")
    if first_space <= 0:
        raise ValueError("missing token")

    token = payload[:first_space]
    file_name = payload[first_space + 1:].strip()
    if not file_name:
        raise ValueError("missing file name")

    return token, file_name


def _lookup_transfer(token: str) -> sqlite3.Row | None:
    if not DB_PATH.exists():
        return None

    with DB_LOCK:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            return connection.execute(
                "SELECT token, user_id, action, file_id, file_name, file_size, expires_at, status FROM pending_transfers WHERE token = ?",
                (token,),
            ).fetchone()
        finally:
            connection.close()


def _consume_transfer(token: str) -> None:
    if not DB_PATH.exists():
        return

    with DB_LOCK:
        connection = sqlite3.connect(DB_PATH)
        try:
            connection.execute(
                "UPDATE pending_transfers SET status = 'consumed' WHERE token = ?",
                (token,),
            )
            connection.commit()
        finally:
            connection.close()


def _store_file_record(user_id: str, file_name: str, file_size: int, checksum_sha256: str) -> str:
    file_id = secrets.token_urlsafe(16)
    if not DB_PATH.exists():
        return file_id

    with DB_LOCK:
        connection = sqlite3.connect(DB_PATH)
        try:
            connection.execute(
                "INSERT INTO files (id, owner_id, name, size, checksum_sha256, uploaded_at) VALUES (?, ?, ?, ?, ?, ?)",
                (file_id, user_id, file_name, file_size,
                 checksum_sha256, _now_iso()),
            )
            connection.commit()
        finally:
            connection.close()
    return file_id


def _get_file_checksum(owner_id: str, file_name: str) -> str | None:
    if not DB_PATH.exists():
        return None

    with DB_LOCK:
        connection = sqlite3.connect(DB_PATH)
        connection.row_factory = sqlite3.Row
        try:
            row = connection.execute(
                "SELECT checksum_sha256 FROM files WHERE owner_id = ? AND name = ? ORDER BY uploaded_at DESC LIMIT 1",
                (owner_id, file_name),
            ).fetchone()
            if row is None:
                return None
            return row["checksum_sha256"]
        finally:
            connection.close()


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file_handle:
        while True:
            chunk = file_handle.read(CHUNK_SIZE)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _write_upload(connection: ssl.SSLSocket, token: str, file_name: str, file_size: int) -> None:
    transfer = _lookup_transfer(token)
    if transfer is None or transfer["action"] != "upload" or transfer["status"] != "pending":
        connection.sendall(b"ERROR invalid or expired token\n")
        return

    user_dir = STORAGE_DIR / transfer["user_id"]
    user_dir.mkdir(parents=True, exist_ok=True)
    target_path = user_dir / _safe_name(file_name)

    connection.sendall(b"READY\n")
    remaining = file_size
    digest = hashlib.sha256()
    with target_path.open("wb") as file_handle:
        while remaining > 0:
            chunk = connection.recv(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            file_handle.write(chunk)
            digest.update(chunk)
            remaining -= len(chunk)

    if remaining == 0:
        checksum_sha256 = digest.hexdigest()
        _store_file_record(transfer["user_id"],
                           _safe_name(file_name), file_size, checksum_sha256)
        _consume_transfer(token)
        connection.sendall(b"SUCCESS\n")
    else:
        connection.sendall(b"ERROR incomplete upload\n")


def _handle_client(connection: ssl.SSLSocket, address: tuple[str, int]) -> None:
    try:
        line = _recv_line(connection)
        if not line:
            return

        upper_line = line.upper()
        if upper_line.startswith("UPLOAD "):
            token, file_name, file_size = _parse_upload_command(line)
            _write_upload(connection, token, file_name, file_size)
        elif upper_line.startswith("DOWNLOAD "):
            token, raw_file_name = _parse_download_command(line)
            file_name = _safe_name(raw_file_name)
            transfer = _lookup_transfer(token)
            if transfer is None or transfer["action"] != "download" or transfer["status"] != "pending":
                connection.sendall(b"ERROR invalid or expired token\n")
                return

            user_dir = STORAGE_DIR / transfer["user_id"]
            target_path = user_dir / file_name
            if not target_path.exists():
                connection.sendall(b"ERROR file not found\n")
                return

            expected_checksum = _get_file_checksum(
                transfer["user_id"], file_name)
            if expected_checksum is not None:
                actual_checksum = _file_sha256(target_path)
                if actual_checksum != expected_checksum:
                    connection.sendall(b"ERROR checksum mismatch\n")
                    return

            file_size = target_path.stat().st_size
            connection.sendall(f"SIZE {file_size}\n".encode("utf-8"))
            with target_path.open("rb") as file_handle:
                while True:
                    chunk = file_handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    connection.sendall(chunk)
            _consume_transfer(token)
        else:
            connection.sendall(b"ERROR unsupported command\n")
    except ValueError as exc:
        try:
            connection.sendall(f"ERROR {exc}\n".encode("utf-8"))
        except Exception:
            pass
    except Exception as exc:  # pragma: no cover - temporary server safeguard
        try:
            connection.sendall(f"ERROR {exc}\n".encode("utf-8"))
        except Exception:
            pass
    finally:
        connection.close()


def main() -> None:
    STORAGE_DIR.mkdir(parents=True, exist_ok=True)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    if CERT_FILE.exists() and KEY_FILE.exists():
        context.load_cert_chain(certfile=str(CERT_FILE), keyfile=str(KEY_FILE))
    else:
        raise FileNotFoundError("TLS certificate files are missing in certs/")

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server_socket:
        server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server_socket.bind((HOST, PORT))
        server_socket.listen(5)
        print(f"SecureDrop socket server listening on {HOST}:{PORT}")

        while True:
            client_socket, address = server_socket.accept()
            connection = context.wrap_socket(client_socket, server_side=True)
            threading.Thread(target=_handle_client, args=(
                connection, address), daemon=True).start()


if __name__ == "__main__":
    main()
