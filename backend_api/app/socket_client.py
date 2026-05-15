from __future__ import annotations

import os
import socket
import ssl
from typing import BinaryIO, Generator

CHUNK_SIZE = 32 * 1024


def _build_client_context() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


def upload_file(socket_host: str, socket_port: int, token: str, file_name: str, file_stream: BinaryIO, file_size: int) -> None:
    context = _build_client_context()
    with socket.create_connection((socket_host, socket_port), timeout=30) as raw_socket:
        with context.wrap_socket(raw_socket, server_hostname=socket_host) as secure_socket:
            secure_socket.sendall(
                f"UPLOAD {token} {file_name} {file_size}\n".encode("utf-8"))
            response = _read_line(secure_socket)
            if response != "READY":
                raise RuntimeError(response or "Socket server rejected upload")

            remaining = file_size
            while remaining > 0:
                chunk = file_stream.read(min(CHUNK_SIZE, remaining))
                if not chunk:
                    break
                secure_socket.sendall(chunk)
                remaining -= len(chunk)

            final_response = _read_line(secure_socket)
            if not final_response.startswith("SUCCESS"):
                raise RuntimeError(final_response or "Socket upload failed")


def download_file(socket_host: str, socket_port: int, token: str, file_name: str) -> Generator[bytes, None, None]:
    context = _build_client_context()
    raw_socket = socket.create_connection(
        (socket_host, socket_port), timeout=30)
    secure_socket = context.wrap_socket(
        raw_socket, server_hostname=socket_host)
    try:
        secure_socket.sendall(
            f"DOWNLOAD {token} {file_name}\n".encode("utf-8"))
        header = _read_line(secure_socket)
        if not header.startswith("SIZE "):
            raise RuntimeError(header or "Socket server rejected download")

        remaining = int(header.split(" ", 1)[1])
        while remaining > 0:
            chunk = secure_socket.recv(min(CHUNK_SIZE, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk
    finally:
        secure_socket.close()


def _read_line(connection: ssl.SSLSocket) -> str:
    data = bytearray()
    while True:
        chunk = connection.recv(1)
        if not chunk:
            break
        data.extend(chunk)
        if data.endswith(b"\n"):
            break
    return data.decode("utf-8", errors="replace").strip()
