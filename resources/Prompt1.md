This is a comprehensive, unified project specification that combines all requirements from both documents. Nothing is omitted; the React/Next.js frontend from the second document is integrated with the core networking requirements from the first. This plan provides a clear architecture, implementation steps, and code guidance to achieve a top-grade submission.

## 🚀 Secure File Transfer Web Application – Complete Project Specification

### 1. Unified Project Goal

Build a full‑stack secure file transfer application that **simulates a cloud storage service** (like Google Drive/Dropbox) while **demonstrating low‑level networking concepts**. The system must:

- Use a **modern React/Next.js frontend** for a polished user experience.
- Use a **Python backend** that combines a **REST API server** (Flask/FastAPI) and a **raw TCP socket server**.
- Encrypt **all file transfer data** with **SSL/TLS**.
- Handle multiple concurrent clients using **multithreading**.
- Cover all mandatory course topics (TCP, TLS, multithreading, IPC, RPC concepts, UDP comparison, etc.).

---

### 2. System Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                         User's Browser                               │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │         React / Next.js Frontend (TailwindCSS)                │  │
│  │  - Login / Register                                            │  │
│  │  - Dashboard with file list, upload (drag & drop), download    │  │
│  │  - Communicates with Backend API via HTTPS (HTTP)              │  │
│  └───────────────────────────────┬───────────────────────────────┘  │
└──────────────────────────────────┼──────────────────────────────────┘
                                   │ HTTPS (REST API)
                                   ▼
┌─────────────────────────────────────────────────────────────────────┐
│                  Python Backend Web Server (Flask / FastAPI)         │
│  - Handles authentication, session management (JWT)                  │
│  - Exposes REST endpoints: /api/login, /api/files, etc.             │
│  - Delegates actual file transfers to the TCP Socket Layer           │
│  - May use inter‑process communication (queues) for logging/audit    │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ Internal communication
                                │ (e.g., loopback socket or queue)
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│           Python TCP Socket Server (Core Networking Layer)           │
│  - Listens on a dedicated port (e.g., 9000) with SSL/TLS            │
│  - Receives file chunks, stores files on disk                        │
│  - Sends files in chunks for downloads                               │
│  - Each client connection handled in a separate thread               │
│  - Implements all low‑level networking requirements                  │
└───────────────────────────────┬─────────────────────────────────────┘
                                │
                                ▼
                          File System Storage
                       (user‑specific directories)
```

---

### 3. Frontend Requirements (React / Next.js)

#### Technology Stack

- **Next.js** (App Router) **or** React + Vite (choose based on preference)
- **TailwindCSS** for modern styling
- **Axios** for HTTP requests
- **React Hook Form** + **Zod** for form validation

#### Required Pages & Features

| Page         | Description                                                                     |
| ------------ | ------------------------------------------------------------------------------- |
| `/login`     | Username/password login form. On success, store JWT token in localStorage.      |
| `/register`  | Registration form with password confirmation.                                   |
| `/dashboard` | Main file management interface.                                                 |
|              | - **File list**: Table or grid view with name, size, upload date.               |
|              | - **Upload area**: Drag & drop zone + browse button.                            |
|              | - **Download button** for each file.                                            |
|              | - **Delete button** (optional).                                                 |
|              | - **Progress bar** showing upload/download progress (using Axios interceptors). |

#### Frontend – Backend Communication

All API calls go to the Flask/FastAPI server (e.g., `http://localhost:5000/api`).  
**Endpoints used by frontend:**

| Method | Endpoint                        | Purpose                                          |
| ------ | ------------------------------- | ------------------------------------------------ |
| POST   | `/api/auth/register`            | Register new user                                |
| POST   | `/api/auth/login`               | Authenticate, return JWT                         |
| GET    | `/api/files`                    | List all files belonging to the logged‑in user   |
| POST   | `/api/upload-request`           | Request an upload token / socket connection info |
| GET    | `/api/download-request/:fileId` | Request a download token / socket info           |
| DELETE | `/api/files/:fileId`            | Delete a file (optional)                         |

_Note:_ The actual file bytes **never** travel through the HTTP API. Instead, the API returns connection details (e.g., port, one‑time token) for the TCP socket server. The frontend then opens a secure WebSocket‑like connection (or raw TCP via a bridge) to transfer the file. For simplicity in a web browser (which cannot do raw TCP sockets), we will implement a **WebSocket‑to‑TCP bridge** inside the Python backend. This is a common pattern that satisfies the "low‑level TCP + TLS" requirement while still being usable from a browser.

**Alternative for pure TCP demonstration:**  
The student may also build a separate CLI client in Python that directly uses the TCP socket layer, proving the socket programming works independently. The web frontend can still use the bridge.

---

### 4. Backend Web Server (Flask / FastAPI)

#### Responsibilities

- User management (SQLite or JSON file for simplicity)
- Password hashing with **bcrypt**
- JWT token generation and verification
- Managing metadata about files (filename, owner, size, upload date)
- Providing connection parameters for the TCP socket layer

#### API Endpoints Detailed

```python
# Example FastAPI endpoints

@app.post("/api/auth/register")
async def register(user: UserCreate):
    # Hash password, store in DB, return success

@app.post("/api/auth/login")
async def login(credentials: UserLogin):
    # Validate, return JWT access token

@app.get("/api/files")
async def list_files(current_user = Depends(get_current_user)):
    # Return list of file metadata for the user

@app.post("/api/upload-request")
async def request_upload(file_name: str, file_size: int, current_user = Depends(get_current_user)):
    # Generate a unique upload token
    # Return: { "socket_port": 9000, "token": "abc123", "server_ip": "127.0.0.1" }
```

#### Communication with TCP Socket Layer

The API server and the TCP socket server run in separate processes or threads. They share information via:

- A **multiprocessing.Queue** (IPC) to pass upload/download tokens and metadata.
- A small **shared database table** (e.g., `pending_transfers`).

When the frontend requests an upload, the API creates a record with a unique token and expected file metadata. The TCP server, upon receiving a connection, expects the first message to contain this token, thereby linking the socket connection to a specific user and file operation.

---

### 5. TCP Socket File Transfer Layer (Core Networking)

This is the **most important** part for the course. It must be implemented from scratch using Python's `socket` and `ssl` modules.

#### Design

- **Listening socket**: bound to `0.0.0.0:9000`, wrapped with SSL/TLS.
- **Multithreaded**: each `accept()` spawns a new `threading.Thread` that handles one client.
- **Protocol**: a simple text/binary protocol over the encrypted stream.
  - First message (newline‑terminated): `UPLOAD <token> <filename> <filesize>` or `DOWNLOAD <token> <filename>`.
  - After server acknowledgment, the client sends/receives raw file bytes in chunks (e.g., 4096 bytes).
- **File storage**: files are saved in a directory structure like `./storage/<username>/<filename>`.

#### SSL/TLS Setup

Generate a self‑signed certificate:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

Load it in Python:

```python
import ssl

context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind(('0.0.0.0', 9000))
server_socket.listen(5)

# Wrap with SSL
secure_socket = context.wrap_socket(server_socket, server_side=True)
```

#### Threaded Client Handler (Simplified)

```python
def handle_client(conn, addr):
    try:
        # Read the command line (e.g., "UPLOAD token file.txt 1024")
        command = conn.recv(1024).decode().strip()
        cmd_parts = command.split()
        if cmd_parts[0] == "UPLOAD":
            token = cmd_parts[1]
            filename = cmd_parts[2]
            filesize = int(cmd_parts[3])
            # Validate token with the shared queue/DB
            if not validate_token(token, addr, filename, filesize):
                conn.send(b"ERROR Invalid token\n")
                return
            conn.send(b"READY\n")
            # Receive file in chunks
            with open(storage_path, 'wb') as f:
                remaining = filesize
                while remaining > 0:
                    chunk = conn.recv(min(4096, remaining))
                    if not chunk:
                        break
                    f.write(chunk)
                    remaining -= len(chunk)
            conn.send(b"SUCCESS\n")
        elif cmd_parts[0] == "DOWNLOAD":
            # Similar logic: read file from disk and send in chunks
            pass
    finally:
        conn.close()
```

#### Concurrency Demonstration

The server must handle **multiple simultaneous uploads/downloads**. Each thread runs independently, and file I/O operations are thread‑safe as long as each file is unique.

---

### 6. Integration: Bridging Browser to TCP Socket

Since browsers cannot open raw TCP sockets, we implement a **WebSocket proxy** inside the same Python backend (or a separate process) that bridges WebSocket messages to the TCP socket server.

**Approach:**

- Frontend uses `new WebSocket('wss://localhost:5000/ws')`.
- The WebSocket server (e.g., using `websockets` library or FastAPI's WebSocket support) receives messages like `{ "action": "upload", "token": "...", "chunk": "base64..." }`.
- The WebSocket server connects to the TCP socket server (on localhost:9000) using a plain TCP socket (with TLS), forwards the command, then pipes chunks.
- This satisfies the requirement because **the actual file transfer still occurs over a TLS‑encrypted TCP socket**; the WebSocket layer is merely a browser‑compatible transport.

**Alternative (Cleaner for Demonstration):**  
Build a **simple Python CLI client** that uses the TCP socket layer directly, and show both the web UI and the CLI client working with the same backend. This explicitly proves the socket programming requirement.

---

### 7. Course Topic Coverage Checklist

| Topic                             | How It Is Demonstrated                                                                     |
| --------------------------------- | ------------------------------------------------------------------------------------------ |
| Client‑Server Model               | Browser (client) ↔ API server; API server ↔ TCP socket server; CLI client ↔ socket server. |
| IP Addresses, Ports, Sockets      | TCP socket server listens on a specific port; client connects to IP:port.                  |
| TCP Socket Programming            | Custom protocol over TCP streams; chunked file transfer.                                   |
| Multithreaded TCP Server          | `threading.Thread` per client connection.                                                  |
| SSL/TLS Secure Sockets ⭐         | `ssl.wrap_socket()` with self‑signed certificate.                                          |
| Non‑blocking I/O (optional)       | Can be added using `selectors` or `asyncio` for advanced scalability.                      |
| UDP Datagram Sockets (comparison) | Implement a separate UDP notification service that broadcasts “new file uploaded”.         |
| IP Multicast (bonus)              | Extend UDP service to use multicast group for notifications.                               |
| RMI / RPC Concept                 | File operations (`uploadFile`, `downloadFile`) are remote services invoked via the API.    |
| Interprocess Communication (IPC)  | API server and TCP server communicate via multiprocessing.Queue or a shared SQLite DB.     |

---

### 8. Security Implementation Details

- **TLS Encryption**: All socket data (commands and file bytes) is encrypted.
- **Password Hashing**: Use `bcrypt` (recommended) or `hashlib.pbkdf2_hmac`.
- **JWT Tokens**: Signed with HS256, stored in browser `localStorage`; included in `Authorization: Bearer <token>` header.
- **File Validation**: Check file size limits, sanitize filenames to prevent path traversal attacks.
- **MITM Protection**: TLS certificate validation (in a real deployment, use a proper CA; for demo, self‑signed with explicit trust in the browser).

---

### 9. Optional Advanced Features (for Higher Grade)

| Feature                       | Implementation Suggestion                                                                         |
| ----------------------------- | ------------------------------------------------------------------------------------------------- |
| Drag & Drop Upload            | Use `react-dropzone` library.                                                                     |
| Upload/Download Progress Bar  | Axios `onUploadProgress` / WebSocket chunk acknowledgments.                                       |
| Resume Interrupted Transfers  | Store partial file size; client requests offset in `DOWNLOAD` command.                            |
| File Integrity (SHA‑256)      | Compute hash on server after upload, return to client for verification.                           |
| Real‑time Notifications       | WebSocket or UDP multicast to notify all connected clients of new file uploads.                   |
| Logging / Audit Trail         | Write all operations to a log file with timestamp, user, IP, and action.                          |
| TCP vs UDP Performance Report | Conduct experiments transferring same file over TCP and UDP (with reliability layer) and compare. |

---

### 10. Step‑by‑Step Implementation Plan

1. **Set up project structure**:

   ```
   project/
   ├── frontend/           # Next.js app
   ├── backend_api/        # Flask/FastAPI app
   ├── socket_server/      # TCP + TLS server
   ├── certs/              # key.pem, cert.pem
   ├── storage/            # User file storage
   └── README.md
   ```

2. **Implement TCP Socket Server** (without TLS first) with threading and file transfer logic.

3. **Add SSL/TLS** to the socket server using self‑signed certificates.

4. **Build Flask/FastAPI backend** with user authentication (JWT) and file metadata management.

5. **Integrate token‑based coordination** between API and socket server (e.g., using a shared dictionary protected by a lock, or a tiny SQLite table).

6. **Create React/Next.js frontend**:
   - Authentication pages.
   - Dashboard with file list, upload, download.
   - Connect to API endpoints.

7. **Implement WebSocket bridge** (or CLI client) to enable browser file transfers.

8. **Add optional features**: UDP notification service, progress bars, etc.

9. **Write academic report** explaining architecture, networking concepts, security, and a demo guide.

10. **Test thoroughly** with multiple concurrent users.

---

### 11. Suggestions for Top Grade

- **Demonstrate the TLS handshake** explicitly in the report with Wireshark screenshots (or `openssl s_client` output).
- **Show the difference** between encrypted and unencrypted traffic by temporarily disabling TLS for a test transfer.
- **Provide a clear, well‑commented codebase** with a `README.md` that includes setup instructions, certificate generation, and a demo script.
- **Include a comparison of TCP vs UDP** for file transfer (even a simple table with observations on speed and reliability).
- **Explain scalability**: discuss how a multithreaded server compares to an asynchronous (`asyncio`) version.
- **Mention real‑world parallels**: AWS S3, Dropbox, and how they use TLS and chunked transfers.

---

### 12. Final Deliverables Checklist

- [ ] Full source code (frontend + backend API + TCP socket server).
- [ ] SSL/TLS certificate files and generation script.
- [ ] System architecture diagram (as an image in the report).
- [ ] Step‑by‑step demo instructions (how to run everything locally).
- [ ] Academic report covering all course topics listed.
- [ ] (Optional) Performance comparison data.

This unified specification ensures that **every requirement from both documents** is addressed. You now have a complete blueprint to build a project that is both academically rigorous and impressive as a modern web application.
