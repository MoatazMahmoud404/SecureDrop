from __future__ import annotations

import os
import secrets
from pathlib import Path

import requests

BASE_URL = "http://127.0.0.1:8000"
WORK_DIR = Path(__file__).resolve().parents[1]


def main() -> None:
    username = f"user_{secrets.token_hex(4)}"
    password = "DemoPass123!"

    register_response = requests.post(
        f"{BASE_URL}/api/auth/register",
        json={"username": username, "password": password},
        timeout=30,
    )
    register_response.raise_for_status()

    login_response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": username, "password": password},
        timeout=30,
    )
    login_response.raise_for_status()
    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    upload_source = WORK_DIR / "storage" / "e2e-source.txt"
    upload_source.parent.mkdir(parents=True, exist_ok=True)
    source_payload = f"SecureDrop e2e payload {secrets.token_hex(16)}\n".encode(
        "utf-8")
    upload_source.write_bytes(source_payload)

    with upload_source.open("rb") as handle:
        upload_response = requests.post(
            f"{BASE_URL}/api/upload-commit",
            headers=headers,
            files={"file": (upload_source.name, handle,
                            "application/octet-stream")},
            timeout=60,
        )
    upload_response.raise_for_status()

    files_response = requests.get(
        f"{BASE_URL}/api/files", headers=headers, timeout=30)
    files_response.raise_for_status()
    files = files_response.json()
    if not files:
        raise RuntimeError("No files returned after upload")

    target = next(
        (item for item in files if item["name"] == upload_source.name), files[0])
    file_id = target["id"]

    download_response = requests.get(
        f"{BASE_URL}/api/download-commit/{file_id}",
        headers=headers,
        timeout=60,
    )
    download_response.raise_for_status()

    downloaded = WORK_DIR / "storage" / "e2e-downloaded.txt"
    downloaded.write_bytes(download_response.content)

    if downloaded.read_bytes() != source_payload:
        raise RuntimeError(
            "Downloaded payload does not match uploaded payload")

    delete_response = requests.delete(
        f"{BASE_URL}/api/files/{file_id}",
        headers=headers,
        timeout=30,
    )
    delete_response.raise_for_status()

    print("E2E PASS")
    print(f"username={username}")
    print(f"uploaded_file={upload_source.name}")
    print(f"file_id={file_id}")


if __name__ == "__main__":
    main()
