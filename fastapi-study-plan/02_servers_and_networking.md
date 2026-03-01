# Module 02: Servers and Networking

## Learning Objectives

By the end of this module, you will be able to:

- Define what a server is (hardware and software)
- Explain client-server architecture
- Describe TCP/IP at a practical level
- Explain what ports are and why they matter
- Trace the full request/response lifecycle
- Explain what a reverse proxy does
- Build a minimal HTTP server from scratch

---

## 2.1 What Is a Server?

A server is **a program that listens for incoming requests and sends back responses**. That is the entire definition.

The word "server" is overloaded:
- **Hardware server**: A physical computer in a data center
- **Software server**: A program running on that computer (or your laptop)

Your laptop can be a server. When you run `python3 -m http.server 8000`, your laptop is serving HTTP requests. The only difference between your laptop and a "real" server is reliability, scale, and network configuration.

### Mental Model

```
A server is a waiter in a restaurant.

1. Waiter stands ready (listening)
2. Customer places order (request)
3. Waiter takes order to kitchen (processing)
4. Kitchen prepares food (business logic)
5. Waiter brings food back (response)
6. Waiter goes back to standing ready (listening again)
```

The key behavior: **listen → receive → process → respond → repeat.**

---

## 2.2 Client vs Server

```
┌──────────┐         Request          ┌──────────┐
│          │ ───────────────────────► │          │
│  CLIENT  │                          │  SERVER  │
│          │ ◄─────────────────────── │          │
└──────────┘         Response         └──────────┘

 Initiates          Listens
 connection         Waits
 Sends request      Processes
 Receives response  Sends response
```

**Client**: The entity that initiates a request. A browser, a mobile app, a `curl` command, another server.

**Server**: The entity that listens for and responds to requests.

A program can be both. Your API server is a server to the browser but a client to the database.

```
Browser ──► Your API Server ──► Database
(client)    (server & client)   (server)
```

---

## 2.3 TCP/IP — The Foundation

### IP (Internet Protocol)

IP handles **addressing**. Every device on the internet has an IP address.

- **IPv4**: `192.168.1.1` (4 bytes, ~4.3 billion addresses)
- **IPv6**: `2001:0db8:85a3::8a2e:0370:7334` (16 bytes, practically unlimited)

Special addresses:
```
127.0.0.1    → localhost (your own machine)
0.0.0.0      → all interfaces on this machine
192.168.x.x  → private network (not routable on internet)
10.x.x.x     → private network
172.16-31.x.x → private network
```

### TCP (Transmission Control Protocol)

TCP handles **reliable delivery**. It guarantees:
1. Data arrives in order
2. Lost packets are retransmitted
3. Duplicate packets are discarded
4. Connection is established before data flows

### The Three-Way Handshake

```
Client                    Server
  │                         │
  │ ── SYN ──────────────► │   "I want to connect"
  │                         │
  │ ◄── SYN-ACK ────────── │   "OK, I acknowledge"
  │                         │
  │ ── ACK ──────────────► │   "Great, we're connected"
  │                         │
  │   [Connection established - data can flow]
  │                         │
```

### TCP vs UDP

| Feature | TCP | UDP |
|---------|-----|-----|
| Reliable | Yes | No |
| Ordered | Yes | No |
| Connection | Required (handshake) | None |
| Speed | Slower | Faster |
| Use case | HTTP, email, file transfer | Video streaming, DNS, gaming |

HTTP uses TCP because reliability matters more than speed for web requests.

### Exercise 2.1: See TCP in Action

```bash
# Watch a TCP connection being established
# The -v flag shows connection details
curl -v http://httpbin.org/get 2>&1 | head -20

# See all active TCP connections on your machine
# macOS:
netstat -an | grep ESTABLISHED | head -10

# Linux:
ss -tuln
```

---

## 2.4 Ports

A port is a number (0–65535) that identifies a specific service on a machine. Think of it as an apartment number in a building — the IP address is the building, the port is the unit.

### Well-Known Ports

```
Port 22    → SSH
Port 25    → SMTP (email)
Port 53    → DNS
Port 80    → HTTP
Port 443   → HTTPS
Port 3000  → Common dev server (Node.js)
Port 3306  → MySQL
Port 5432  → PostgreSQL
Port 5672  → RabbitMQ
Port 6379  → Redis
Port 8000  → Common dev server (Python/FastAPI)
Port 8080  → Common alternative HTTP
Port 27017 → MongoDB
```

### How It Works

When you visit `https://google.com`, the browser connects to `142.250.80.46:443`. The `:443` is implied by `https://`.

```
http://example.com      → example.com:80
https://example.com     → example.com:443
http://localhost:8000   → 127.0.0.1:8000
```

### Port Binding

When a server starts, it **binds** to a port. Only one process can bind to a port at a time. If port 8000 is taken:

```
ERROR: [Errno 48] Address already in use
```

### Exercise 2.2: Explore Ports

```bash
# Start a simple HTTP server on port 8000
python3 -m http.server 8000 &

# Verify it's listening
# macOS:
lsof -i :8000
# Linux:
ss -tlnp | grep 8000

# Try to start another server on the same port
python3 -m http.server 8000
# Observe the error

# Kill the background server
kill %1

# See what's running on common ports
# macOS:
lsof -i -P | grep LISTEN
# Linux:
ss -tlnp
```

---

## 2.5 The Full Request/Response Lifecycle

Here is the complete journey of an API request, from your code to the server and back.

```
┌─────────────────────────────────────────────────────────────┐
│                     YOUR APPLICATION                         │
│  response = requests.get("https://api.example.com/users/1") │
└──────────────────────────┬──────────────────────────────────┘
                           │
                    ① DNS Resolution
                    "api.example.com" → 93.184.216.34
                           │
                    ② TCP Handshake
                    Connect to 93.184.216.34:443
                           │
                    ③ TLS Handshake
                    Negotiate encryption
                           │
                    ④ Send HTTP Request
                    ┌──────────────────────┐
                    │ GET /users/1 HTTP/1.1│
                    │ Host: api.example.com│
                    │ Accept: app/json     │
                    └──────────┬───────────┘
                               │
              ┌────── INTERNET (routers, switches, cables) ──────┐
              │                                                   │
              └───────────────────┬───────────────────────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │      REVERSE PROXY         │
                    │   (nginx / load balancer)  │
                    │   Port 443 → Port 8000     │
                    └─────────────┬──────────────┘
                                  │
                    ┌─────────────▼──────────────┐
                    │      APPLICATION SERVER     │
                    │   (uvicorn + FastAPI)       │
                    │                             │
                    │ 1. Parse request            │
                    │ 2. Route to handler         │
                    │ 3. Validate input           │
                    │ 4. Execute business logic   │
                    │ 5. Query database           │
                    │ 6. Serialize response       │
                    │ 7. Return HTTP response     │
                    └─────────────┬──────────────┘
                                  │
                    ⑤ HTTP Response travels back
                    ┌──────────────────────────┐
                    │ HTTP/1.1 200 OK           │
                    │ Content-Type: app/json    │
                    │                           │
                    │ {"id":1,"name":"Alice"}   │
                    └──────────────┬────────────┘
                                   │
                    ⑥ TCP Connection closed
                    (or kept alive for reuse)
                                   │
                    ┌──────────────▼────────────┐
                    │  YOUR APPLICATION          │
                    │  response.status_code: 200 │
                    │  response.json(): {...}    │
                    └───────────────────────────┘
```

### What Takes Time

```
DNS lookup:       ~10-100ms (cached: ~0ms)
TCP handshake:    ~10-50ms
TLS handshake:    ~30-100ms
Server processing: ~5-500ms (depends on work)
Data transfer:    ~5-100ms (depends on size/distance)
───────────────────────────────
Total:            ~60-850ms for a typical API call
```

This is why:
- DNS caching matters
- Connection reuse (keep-alive) matters
- Server-side performance matters
- Geographical proximity matters (CDNs)

---

## 2.6 Building a Server from Scratch

To truly understand servers, build one.

### The Simplest Possible Server (Python, no frameworks)

```python
# bare_server.py
import socket

HOST = "127.0.0.1"
PORT = 8000

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_socket.bind((HOST, PORT))
server_socket.listen(1)

print(f"Server listening on {HOST}:{PORT}")

while True:
    client_socket, client_address = server_socket.accept()
    print(f"Connection from {client_address}")

    request_data = client_socket.recv(4096).decode("utf-8")
    print(f"Request:\n{request_data}")

    request_line = request_data.split("\r\n")[0]
    method, path, _ = request_line.split(" ")

    if path == "/":
        body = '{"message": "Hello from bare socket server!"}'
        status = "200 OK"
    elif path == "/health":
        body = '{"status": "healthy"}'
        status = "200 OK"
    else:
        body = '{"error": "Not found"}'
        status = "404 Not Found"

    response = (
        f"HTTP/1.1 {status}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
        f"{body}"
    )

    client_socket.sendall(response.encode("utf-8"))
    client_socket.close()
```

### Exercise 2.3: Run and Test Your Server

```bash
# Terminal 1: Start the server
python3 bare_server.py

# Terminal 2: Test it
curl http://localhost:8000/
curl http://localhost:8000/health
curl http://localhost:8000/nonexistent
curl -v http://localhost:8000/
```

**Study what happens:**
1. What does the server print when a request arrives?
2. Can you see the raw HTTP request?
3. What happens if you open `http://localhost:8000` in your browser?
4. Why does the browser make multiple requests?

### Exercise 2.4: Extend the Server

Modify `bare_server.py` to:

1. Handle POST requests — read the body and echo it back
2. Return the current time at `/time`
3. Return request headers at `/headers`
4. Log each request with timestamp to a file

---

## 2.7 From Sockets to Frameworks

The server above handles one request at a time and requires manual HTTP parsing. Real servers need:

- **Concurrency**: Handle thousands of simultaneous connections
- **Routing**: Map URLs to handler functions cleanly
- **Parsing**: Parse headers, query params, JSON bodies automatically
- **Validation**: Check input correctness
- **Error handling**: Graceful failure with proper status codes

This is what frameworks do. The evolution:

```
Raw sockets (bare_server.py)
    ↓
WSGI servers (gunicorn + Flask)     ← synchronous
    ↓
ASGI servers (uvicorn + FastAPI)    ← asynchronous
```

**WSGI** (Web Server Gateway Interface): Python standard for synchronous web servers.
**ASGI** (Asynchronous Server Gateway Interface): Python standard for async web servers. FastAPI uses this.

---

## 2.8 Reverse Proxies

A reverse proxy sits between the internet and your application server.

```
Internet → Reverse Proxy (nginx) → Application Server (uvicorn)
                │
                ├── Terminates TLS (handles HTTPS)
                ├── Load balances across multiple app servers
                ├── Serves static files directly
                ├── Caches responses
                ├── Rate limits requests
                └── Buffers slow clients
```

### Why Not Expose uvicorn Directly?

1. uvicorn is not designed to handle TLS termination efficiently
2. uvicorn handles one type of traffic — your framework doesn't need to serve static files
3. nginx can handle 10,000+ concurrent connections for static content
4. A reverse proxy provides a security boundary

### Basic nginx Configuration

```nginx
server {
    listen 80;
    server_name api.example.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    }
}
```

You will set this up in the deployment module. For now, understand the concept.

---

## 2.9 Concurrency Models

How do servers handle multiple requests at once?

### Process-Based

```
Master Process
  ├── Worker Process 1 → handles request
  ├── Worker Process 2 → handles request
  ├── Worker Process 3 → handles request
  └── Worker Process 4 → handles request
```

Each worker is an independent OS process. Simple but memory-heavy. (gunicorn default)

### Thread-Based

```
Process
  ├── Thread 1 → handles request
  ├── Thread 2 → handles request
  ├── Thread 3 → handles request
  └── Thread 4 → handles request
```

Threads share memory. Lighter than processes but Python's GIL limits true parallelism.

### Event Loop (Async)

```
Single Thread
  └── Event Loop
       ├── Check: any new connections? → accept
       ├── Check: any data to read? → process
       ├── Check: any responses to send? → send
       └── Check: any DB responses ready? → continue handler
       (cycles thousands of times per second)
```

One thread handles thousands of connections by never blocking. This is what uvicorn + FastAPI uses. It is extremely efficient for I/O-bound work (API calls, database queries, file reads).

---

## Checkpoint Quiz

1. What is the difference between a hardware server and a software server?
2. What does TCP guarantee that UDP does not?
3. What port does HTTPS use by default?
4. Why can't two programs listen on the same port simultaneously?
5. In the request lifecycle, what happens before the HTTP request is sent?
6. What is the purpose of a reverse proxy?
7. What does ASGI stand for? How does it differ from WSGI?
8. Why is the event loop model efficient for I/O-bound work?
9. What does `127.0.0.1` mean?
10. What error do you get if you try to bind to an already-used port?

---

## Common Mistakes

1. **Thinking "server" means a physical machine.** It's software. Your laptop is a server when it runs one.
2. **Forgetting port numbers.** If your server runs on port 8000, you must use `localhost:8000`, not `localhost`.
3. **Not understanding `0.0.0.0` vs `127.0.0.1`.** `127.0.0.1` only accepts connections from your machine. `0.0.0.0` accepts from any network interface (needed for Docker, remote access).
4. **Exposing application servers directly to the internet.** Always put a reverse proxy in front in production.
5. **Confusing async with parallel.** Async is concurrent (one thread, many tasks). Parallel is simultaneous (multiple threads/processes, truly at the same time).

---

## Mini Project: Multi-Route HTTP Server

Build a more complete server (still using raw sockets) that:

1. Serves a JSON API with at least 5 routes
2. Handles GET and POST methods differently
3. Parses query parameters from the URL
4. Returns appropriate status codes (200, 201, 404, 405)
5. Includes a `/stats` endpoint that returns how many requests have been served

This will be ugly and painful. That is the point. After building this, you will deeply appreciate what frameworks do for you.

```python
# multi_route_server.py - Starting point
import socket
import json
from datetime import datetime
from urllib.parse import urlparse, parse_qs

HOST = "127.0.0.1"
PORT = 8000
request_count = 0

def parse_request(raw):
    lines = raw.split("\r\n")
    request_line = lines[0]
    method, full_path, version = request_line.split(" ")

    parsed_url = urlparse(full_path)
    path = parsed_url.path
    query_params = parse_qs(parsed_url.query)

    headers = {}
    body = ""
    header_done = False
    for line in lines[1:]:
        if line == "":
            header_done = True
            continue
        if not header_done:
            key, value = line.split(": ", 1)
            headers[key] = value
        else:
            body += line

    return method, path, query_params, headers, body

def build_response(status_code, status_text, body_dict):
    body = json.dumps(body_dict)
    return (
        f"HTTP/1.1 {status_code} {status_text}\r\n"
        f"Content-Type: application/json\r\n"
        f"Content-Length: {len(body)}\r\n"
        f"\r\n"
        f"{body}"
    )

# TODO: Implement route handling, start the server loop
# This is your exercise. Build it.
```

---

## Next Module

Proceed to `03_rest_api_design.md` →
