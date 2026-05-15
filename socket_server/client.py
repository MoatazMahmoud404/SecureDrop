from __future__ import annotations

import argparse
import socket
import ssl
from pathlib import Path

CHUNK_SIZE = 32 * 1024


def _context() -> ssl.SSLContext:
    context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    return context


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


def upload(host: str, port: int, token: str, file_path: Path) -> None:
    size = file_path.stat().st_size
    file_name = file_path.name

    with socket.create_connection((host, port), timeout=30) as raw_socket:
        with _context().wrap_socket(raw_socket, server_hostname=host) as connection:
            connection.sendall(
                f"UPLOAD {token} {file_name} {size}\n".encode("utf-8"))
            ready = _read_line(connection)
            if ready != "READY":
                raise RuntimeError(f"Upload rejected: {ready}")

            with file_path.open("rb") as handle:
                while True:
                    chunk = handle.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    connection.sendall(chunk)

            result = _read_line(connection)
            print(result)


def download(host: str, port: int, token: str, file_name: str, out_path: Path) -> None:
    with socket.create_connection((host, port), timeout=30) as raw_socket:
        with _context().wrap_socket(raw_socket, server_hostname=host) as connection:
            connection.sendall(
                f"DOWNLOAD {token} {file_name}\n".encode("utf-8"))
            header = _read_line(connection)
            if not header.startswith("SIZE "):
                raise RuntimeError(f"Download rejected: {header}")

            remaining = int(header.split(" ", 1)[1])
            with out_path.open("wb") as handle:
                while remaining > 0:
                    chunk = connection.recv(min(CHUNK_SIZE, remaining))
                    if not chunk:
                        break
                    handle.write(chunk)
                    remaining -= len(chunk)

            print(f"downloaded {out_path} ({out_path.stat().st_size} bytes)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="SecureDrop TLS socket client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9000)

    subparsers = parser.add_subparsers(dest="command", required=True)

    upload_parser = subparsers.add_parser("upload")
    upload_parser.add_argument("--token", required=True)
    upload_parser.add_argument("--file", required=True)

    download_parser = subparsers.add_parser("download")
    download_parser.add_argument("--token", required=True)
    download_parser.add_argument("--name", required=True)
    download_parser.add_argument("--out", required=True)

    args = parser.parse_args()

    if args.command == "upload":
        upload(args.host, args.port, args.token, Path(args.file))
        return

    download(args.host, args.port, args.token, args.name, Path(args.out))


if __name__ == "__main__":
    main()
