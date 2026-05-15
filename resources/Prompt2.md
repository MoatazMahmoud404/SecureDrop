```md
# Secure File Transfer Web Application – Full System Specification & Implementation Guide

## Project Title (Unified)

**Secure File Transfer Web Application using Python (Backend Networking + TCP/SSL/TLS) and Modern Web Frontend (HTML/CSS/JS or React/Next.js)**

## Project Objective

Build a modern, full‑stack, web‑based secure file transfer system where users can upload and download files through a browser interface.  
The system **must** demonstrate low‑level networking concepts (TCP sockets, SSL/TLS, multithreading) – not just a normal web framework CRUD app.

**Goal:** Simulate a real‑world secure cloud file system (Google Drive / Dropbox) while showing deep understanding of network programming, concurrency, and encryption.

---

## Core Idea (Combined)

- **Web browser** acts as the client interface (HTML/CSS/JS or React/Next.js).
- **Python backend server** (Flask or FastAPI) handles HTTP requests, authentication, and session management.
- **Internal TCP socket layer** (Python, SSL/TLS, multithreaded) performs the actual file transfer.
- All socket communication is encrypted with **SSL/TLS** (self‑signed certificates for development).

---

## System Architecture (3 Layers)
```

┌─────────────────────────────────────────────────────────────┐
│ FRONTEND (Browser) │
│ - HTML/CSS/JS or React/Next.js │
│ - Login / Register, file list, upload/download UI │
│ - Communicates with backend via HTTP/REST API │
└───────────────────────────────┬─────────────────────────────┘
│ HTTP (REST)
▼
┌─────────────────────────────────────────────────────────────┐
│ BACKEND WEB SERVER (Python – Flask or FastAPI) │
│ - Handles authentication, sessions (JWT/cookies) │
│ - Exposes endpoints: /login, /files, /upload‑request... │
│ - Bridges frontend with the TCP socket layer │
└───────────────────────────────┬─────────────────────────────┘
│ internal call / subprocess
▼
┌─────────────────────────────────────────────────────────────┐
│ TCP SOCKET FILE TRANSFER LAYER (Python) │
│ - Raw TCP sockets with SSL/TLS encryption │
│ - Multithreaded (one thread per client) │
│ - Handles file upload/download streaming in chunks │
│ - Uses self‑signed certificate for TLS │
└─────────────────────────────────────────────────────────────┘

````

**Storage:** Local filesystem + metadata (e.g., SQLite or JSON file).

---

## Frontend Requirements (Combined – Two Options)

### Option A – Plain HTML/CSS/JS (Minimal, no framework)
- Modern responsive UI (TailwindCSS optional)
- Pages: Login, Dashboard (file list, upload, download, delete)
- Fetch API to communicate with Python backend
- Features: progress bar, drag & drop (optional)

### Option B – React / Next.js (Modern Full‑Stack)
- Recommended: **Next.js** (or React + Vite)
- UI: TailwindCSS, loading states, progress bars, drag & drop
- Authentication pages (Login, Register)
- Dashboard: table/grid of files, upload button, download/delete actions
- Communicates with Python backend via REST API

**Common frontend features (required):**
- Login / Register
- View list of available files
- Upload file (via browser)
- Download file
- Delete file (optional but recommended)
- Loading indicators and error handling

---

## Backend Web Server (Python – Flask or FastAPI)

### Responsibilities
- Handle HTTP requests from frontend (CORS enabled)
- Authenticate users (password hashing with bcrypt or hashlib)
- Manage sessions (JWT tokens or secure cookies)
- Provide API endpoints that **trigger** the TCP socket layer for file transfers
- Store file metadata (filename, owner, size, upload time)

### API Endpoints (Example)

| Method | Endpoint               | Description                          |
|--------|------------------------|--------------------------------------|
| POST   | `/api/register`        | Create new user                      |
| POST   | `/api/login`           | Authenticate, return token           |
| GET    | `/api/files`           | List all files (metadata)            |
| POST   | `/api/upload/request`  | Ask server for a TCP upload port/token |
| POST   | `/api/download/request`| Request download token + file info   |
| DELETE | `/api/files/<id>`      | Delete a file                        |

**Important:** The actual file data is **not** sent over HTTP. The backend responds with connection details (e.g., TCP port, a one‑time token) and the frontend then initiates a direct SSL/TCP socket connection to the file transfer server.

### Code Skeleton (Flask)
```python
# backend_api.py
from flask import Flask, request, jsonify
from flask_cors import CORS
import jwt, bcrypt, sqlite3
import subprocess, threading, uuid

app = Flask(__name__)
CORS(app)

# In‑memory token store for demo
upload_tokens = {}

@app.route('/api/login', methods=['POST'])
def login():
    # verify user, return JWT
    pass

@app.route('/api/upload/request', methods=['POST'])
def request_upload():
    # Generate a token, start a TCP socket server thread if needed,
    # return port and token to client
    token = str(uuid.uuid4())
    upload_tokens[token] = {'user': user, 'filename': request.json['filename']}
    # Start a temporary SSL socket server on a free port (or reuse main socket server)
    return jsonify({'port': 9999, 'token': token})

if __name__ == '__main__':
    app.run(port=5000)
````

---

## TCP Socket File Transfer Layer (Core Networking)

### Requirements

- **Pure Python socket programming** (no high‑level frameworks)
- **TCP** for reliable stream‑based transfer
- **SSL/TLS** wrapping every socket connection
- **Multithreaded** – one thread per connected client
- Handles two operations:
  - **UPLOAD:** Client sends file data in chunks, server writes to disk
  - **DOWNLOAD:** Server reads file from disk and streams to client

### Protocol Design (Simple)

Each connection follows a simple command‑response:

1. Client sends a JSON header:  
   `{"command": "UPLOAD", "token": "xxx", "filename": "myfile.pdf", "filesize": 12345}`
2. Server validates token, then streams raw file bytes.
3. For DOWNLOAD:  
   Client sends `{"command": "DOWNLOAD", "token": "xxx", "filename": "myfile.pdf"}`  
   Server responds with file size, then streams bytes.

### SSL/TLS Setup (Self‑Signed Certificate)

Generate certificate and key:

```bash
openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
```

### Multithreaded SSL TCP Server (Python)

```python
# tcp_ssl_server.py
import socket, ssl, threading, os, json

HOST = '0.0.0.0'
PORT = 9999
CERTFILE = 'cert.pem'
KEYFILE = 'key.pem'

def handle_client(conn_stream):
    """Handle a single SSL‑encrypted client connection."""
    try:
        # Receive the command header (JSON)
        header = conn_stream.recv(1024).decode()
        cmd = json.loads(header)
        if cmd['command'] == 'UPLOAD':
            receive_file(conn_stream, cmd['filename'], cmd['filesize'])
        elif cmd['command'] == 'DOWNLOAD':
            send_file(conn_stream, cmd['filename'])
    except Exception as e:
        print(f"Error: {e}")
    finally:
        conn_stream.close()

def receive_file(conn, filename, filesize):
    with open(f"uploads/{filename}", 'wb') as f:
        remaining = filesize
        while remaining > 0:
            chunk = conn.read(min(4096, remaining))
            if not chunk: break
            f.write(chunk)
            remaining -= len(chunk)

def send_file(conn, filename):
    filepath = f"uploads/{filename}"
    filesize = os.path.getsize(filepath)
    conn.send(json.dumps({'filesize': filesize}).encode())
    with open(filepath, 'rb') as f:
        while chunk := f.read(4096):
            conn.write(chunk)

def main():
    context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    context.load_cert_chain(certfile=CERTFILE, keyfile=KEYFILE)

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM, 0) as sock:
        sock.bind((HOST, PORT))
        sock.listen(5)
        print(f"SSL/TCP server listening on {HOST}:{PORT}")
        while True:
            client_sock, addr = sock.accept()
            ssl_conn = context.wrap_socket(client_sock, server_side=True)
            threading.Thread(target=handle_client, args=(ssl_conn,)).start()

if __name__ == '__main__':
    main()
```

### Frontend TCP Socket Client (Browser JavaScript)

Because browsers cannot open raw TCP sockets, the **backend API** acts as a proxy or the frontend uses a small server‑side endpoint that tunnels the transfer.  
**Alternative design (recommended):**

- The backend API spawns a **temporary thread** that connects to the TCP socket layer and relays file data, or
- Use **WebSockets** (with TLS) as a bridge – but to strictly meet TCP socket requirement, the file transfer must be performed by a native client?

For a pure web app, the most practical approach is:

- The backend API receives the file via HTTP **multipart/form-data**, then the backend uses its own TCP SSL socket client to forward the file to the storage server.  
  This still demonstrates TCP sockets + SSL between backend components.  
  **Therefore:**
- Frontend sends file to Flask backend (HTTP).
- Flask backend opens an SSL/TCP connection to the TCP file server and forwards the data.
- This satisfies “TCP socket programming” because the backend‑to‑storage communication uses raw sockets.

---

## Authentication System

- **User database:** SQLite or JSON file with hashed passwords (bcrypt or hashlib.pbkdf2_hmac).
- **Session management:** JWT tokens (issued by Flask backend) stored in localStorage (React) or HttpOnly cookies.
- **Protection:** All HTTP endpoints require a valid token (except login/register).
- **TLS for HTTP:** Use HTTPS for the Flask server in production (but for demo, Flask runs on HTTP; internal socket layer still has TLS).

---

## File Transfer Features (Detailed)

| Operation    | Flow                                                                                                                                                                                                                                                                                                               |
| ------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Upload**   | 1. Frontend POST /api/upload/request → receives token + port. <br> 2. Frontend sends file as multipart/form‑data to Flask endpoint `/api/upload/commit?token=...`. <br> 3. Flask opens SSL/TCP connection to socket server, sends upload command + file data in chunks. <br> 4. Socket server writes file to disk. |
| **Download** | 1. Frontend GET /api/download/request?filename=... → returns token. <br> 2. Frontend calls `/api/download/commit?token=...`. <br> 3. Flask connects to socket server, requests download, streams file back to frontend.                                                                                            |
| **List**     | Direct HTTP query to Flask (reads metadata DB).                                                                                                                                                                                                                                                                    |
| **Delete**   | HTTP request; Flask deletes file from disk and DB.                                                                                                                                                                                                                                                                 |

**Chunked streaming:** Flask forwards using `shutil.copyfileobj` or manual read/write loops to avoid memory overload.

---

## Networking Concepts Covered (Course Mapping)

1. **Introduction to Network Programming**
   - Client‑server model, IP addresses, ports, sockets (both TCP and UDP).

2. **Internet Addresses, URLs, URIs**
   - Frontend routes (`/login`, `/dashboard`), backend API endpoints (`https://localhost:5000/api/...`).

3. **TCP Socket Programming**
   - Raw TCP sockets for file transfer between Flask backend and storage server; reliable stream‑based communication.

4. **Multithreaded TCP Server**
   - The socket server uses `threading` to handle multiple concurrent file transfers.

5. **Secure Sockets (SSL/TLS)** ⭐
   - `ssl.wrap_socket` or `SSLContext`; TLS handshake, symmetric encryption, certificate validation.

6. **Non‑blocking I/O (optional but recommended)**
   - Can be implemented using `selectors` or `asyncio` for higher scalability; explanation in report.

7. **UDP Datagram Sockets**
   - Compare TCP vs UDP (reliability, ordering, overhead).
   - **Optional demo:** UDP notification service (e.g., “file uploaded” alerts sent to all connected UDP clients).

8. **IP Multicast** (bonus)
   - Server broadcasts “new file uploaded” to multicast group; frontend (or a separate listener) receives real‑time updates.

9. **Remote Method Invocation (RMI) / RPC concept**
   - Represent file operations as remote services: `uploadFile()`, `downloadFile()`, `listFiles()`.
   - Implemented via the JSON command protocol over TCP.

10. **Interprocess Communication (IPC)**
    - Internal server design: separate processes for authentication, file handling, logging; use `multiprocessing.Queue` or `Redis` for coordination.

---

## Security Requirements (All Must Be Demonstrated)

- **TLS encryption** for all socket communication (between Flask backend and storage server).
- **Self‑signed certificates** – provide setup guide.
- **Password hashing** (bcrypt, salt rounds).
- **Protection from MITM / sniffing** – TLS ensures confidentiality.
- **Secure file handling** – validate filenames, limit upload size, scan for malicious content (basic).
- **JWT token expiry** and signature verification.

---

## Optional Advanced Features (Higher Grade)

- Drag & drop file upload UI
- Real‑time progress bar for uploads/downloads (via WebSocket or polling)
- Resume interrupted transfers (byte‑range support)
- File integrity check (SHA‑256 checksum after transfer)
- Logging system (audit trail of all file operations)
- Real‑time notifications using WebSockets or Server‑Sent Events
- Comparison report: TCP vs UDP performance (latency, throughput)
- IP Multicast notifications for file updates

---

## Expected Deliverables (Final Submission)

- **Full source code** (organized folders):
  - `frontend/` – HTML/CSS/JS or React/Next.js project
  - `backend_api/` – Flask/FastAPI application
  - `socket_server/` – Multithreaded SSL/TCP file server
  - `scripts/` – Certificate generation, database init
- **SSL/TLS certificate setup guide** (commands and explanation)
- **System architecture diagram** (image or ASCII)
- **Clear explanation** of each networking concept (in report)
- **Step‑by‑step demo instructions** (how to run and test)
- **Final academic report** (PDF) covering all required topics

---

## Implementation Plan (Step‑by‑Step)

### Phase 1: Setup & Skeleton

1. Create project directories.
2. Generate self‑signed certificate (`cert.pem`, `key.pem`).
3. Implement basic multithreaded TCP SSL server that accepts connections and echoes.
4. Test with a simple Python client (socket + SSL).

### Phase 2: File Transfer Protocol

5. Extend server to handle upload/download commands with JSON headers.
6. Implement chunked file streaming.
7. Add file metadata storage (SQLite table `files`).

### Phase 3: Backend API (Flask)

8. Create Flask app with CORS.
9. Implement user registration / login with JWT.
10. Build endpoints: `/api/upload/request`, `/api/upload/commit`, `/api/download/request`, `/api/download/commit`, `/api/files`.
11. In commit endpoints, open SSL/TCP connection to socket server and relay data.

### Phase 4: Frontend

12. Build login/dashboard UI (React or plain HTML/JS).
13. Integrate with backend API.
14. Add upload with progress (using `axios` or `fetch` with `onUploadProgress`).
15. Implement file list and download buttons.

### Phase 5: Advanced & Polish

16. Add delete functionality.
17. Implement UDP notification or multicast (optional).
18. Write integrity check (SHA‑256).
19. Prepare report and diagrams.

---

## SSL/TLS Setup Guide (Development)

1. **Generate certificate and private key:**
   ```bash
   openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes
   ```
2. **In Python socket server:**
   ```python
   context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
   context.load_cert_chain(certfile="cert.pem", keyfile="key.pem")
   ```
3. **In Python client (backend API connecting to socket server):**
   ```python
   context = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)
   context.check_hostname = False   # for self‑signed
   context.verify_mode = ssl.CERT_NONE
   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   ssl_sock = context.wrap_socket(sock, server_hostname="localhost")
   ssl_sock.connect(("localhost", 9999))
   ```
4. **Explain TLS handshake in report:**
   - ClientHello, ServerHello, Certificate, KeyExchange, ChangeCipherSpec, Finished.
   - Symmetric encryption (AES) after handshake.

---

## Suggestions for Top Grade

- **Document every networking concept** with explicit references to your code.
- **Provide performance measurements** (transfer time vs file size, CPU usage).
- **Compare TCP vs UDP** by implementing a small UDP echo service and measuring loss.
- **Implement IP multicast** for live “file uploaded” notifications.
- **Add unit tests** for socket protocol and authentication.
- **Use asynchronous I/O** (`asyncio` + `ssl`) instead of threads for better scalability – then compare both.
- **Deploy the system** on a cloud VM (e.g., AWS EC2) and document public access.

---

## Final Notes

This merged document contains **all requirements** from both original specifications.  
You can choose either the plain HTML/CSS/JS frontend or React/Next.js – both are acceptable as long as the core networking (TCP, SSL/TLS, multithreading) is clearly demonstrated.  
The architecture ensures that **low‑level socket programming** is not hidden behind a web framework; the file transfer between the backend API and the storage server uses raw Python sockets with SSL/TLS.

**Now you have a complete blueprint to implement and achieve the highest grade.**

```

```
