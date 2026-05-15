# SecureDrop

Implementation starter for a secure file transfer web application with a Next.js frontend, FastAPI backend, and Python TCP/TLS socket server.

## Current status

- Roadmap documented
- Next.js routes implemented for login, registration, and dashboard
- SQLite-backed authentication and transfer records added
- Backend bridge for upload and download commit flows added
- TLS socket server validates pending transfer tokens from SQLite
- CLI socket client added for direct TCP/TLS verification

## Planned stack

- Frontend: Next.js + TailwindCSS
- Backend: FastAPI
- Socket server: Python stdlib `socket` + `ssl` + `threading`
- Storage: SQLite + local filesystem

## Local run order

1. Generate certificates:
   - `powershell -ExecutionPolicy Bypass -File scripts/generate_certs.ps1`
2. Install backend dependencies:
   - `pip install -r backend_api/requirements.txt`
3. Start the socket server:
   - `python socket_server/server.py`
4. Start the API server:
   - `uvicorn backend_api.app.main:app --host 0.0.0.0 --port 8000 --reload`
5. Start the frontend:
   - `cd frontend`
   - `npm install`
   - `npm run dev`

6. Create an admin user for testing:
   - `python scripts/create_admin.py admin`

## API flow

- `POST /api/auth/register` and `POST /api/auth/login` manage authentication.
- `GET /api/files` returns current-user file metadata.
- `POST /api/upload-commit` forwards file bytes from the backend to the socket server.
- `GET /api/download-commit/{file_id}` streams file bytes back through the backend.
- `DELETE /api/files/{file_id}` removes file metadata for the current user.

## Direct socket verification

Use `socket_server/client.py` to verify the raw TLS socket protocol directly:

- Upload:
  - `python socket_server/client.py --host 127.0.0.1 --port 9000 upload --token <token> --file <path>`
- Download:
  - `python socket_server/client.py --host 127.0.0.1 --port 9000 download --token <token> --name <filename> --out <path>`

## Tests

- `tests/test_security.py` covers password hashing and JWT round-tripping.
- `tests/test_db.py` covers SQLite schema initialization.

## Next step

Run the stack end-to-end and add integration tests for upload and download commit flows.
