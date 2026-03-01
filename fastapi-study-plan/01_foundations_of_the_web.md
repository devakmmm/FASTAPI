# Module 01: Foundations of the Web

## Learning Objectives

By the end of this module, you will be able to:

- Explain what the internet is at a physical and logical level
- Trace what happens when you type a URL into a browser
- Define DNS and explain its role
- Describe the HTTP protocol and its components
- Read and construct HTTP requests and responses
- Explain what JSON is and why it dominates web APIs
- Define statelessness and explain its consequences

---

## 1.1 What Is the Internet?

The internet is a network of networks. Physically, it is cables — undersea fiber optic cables, copper wires, wireless signals — connecting computers worldwide. Logically, it is a set of agreed-upon protocols that let those computers exchange data.

### Mental Model

Think of the internet as a postal system:

- Every house (computer) has an address (IP address)
- Letters (packets) are routed through sorting facilities (routers)
- The postal service follows rules (protocols) about how to format addresses and handle mail

The key insight: **the internet is not magic. It is infrastructure with rules.**

### The Stack (Simplified)

```
┌─────────────────────────────┐
│     Application Layer       │  ← HTTP, HTTPS, FTP, SMTP
│     (What you interact with)│
├─────────────────────────────┤
│     Transport Layer         │  ← TCP, UDP
│     (Reliable delivery)     │
├─────────────────────────────┤
│     Network Layer           │  ← IP (addressing & routing)
│     (Finding the path)      │
├─────────────────────────────┤
│     Link Layer              │  ← Ethernet, Wi-Fi
│     (Physical connection)   │
└─────────────────────────────┘
```

You do not need to memorize this. You need to understand that **each layer handles one concern** and relies on the layer below it.

---

## 1.2 What Happens When You Visit google.com

This is the single most important sequence to understand. Every web interaction follows this pattern.

### The Full Sequence

```
You type "google.com" in browser
         │
         ▼
┌─────────────────────┐
│ 1. DNS Resolution   │  Browser asks: "What IP is google.com?"
│    Browser → DNS    │  DNS responds: "142.250.80.46"
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 2. TCP Connection   │  Browser opens connection to 142.250.80.46:443
│    Three-way        │  SYN → SYN-ACK → ACK
│    handshake        │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 3. TLS Handshake    │  Encryption negotiated (HTTPS)
│    (if HTTPS)       │
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 4. HTTP Request     │  GET / HTTP/1.1
│    Browser → Server │  Host: google.com
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 5. Server Process   │  Google's server processes the request,
│                     │  generates HTML
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 6. HTTP Response    │  HTTP/1.1 200 OK
│    Server → Browser │  Content-Type: text/html
│                     │  <html>...</html>
└────────┬────────────┘
         │
         ▼
┌─────────────────────┐
│ 7. Rendering        │  Browser parses HTML, requests CSS/JS/images
│                     │  (each is another HTTP request)
└─────────────────────┘
```

### Key Takeaways

1. **DNS translates names to numbers.** Computers don't understand "google.com". They understand `142.250.80.46`.
2. **TCP ensures reliable delivery.** It guarantees packets arrive in order and retransmits lost ones.
3. **HTTP is the conversation format.** It defines how client and server talk.
4. **A single page load triggers many requests.** HTML, CSS, JS, images — each is a separate HTTP request.

---

## 1.3 DNS — The Internet's Phone Book

### What DNS Does

DNS (Domain Name System) translates human-readable domain names into IP addresses.

```
google.com  →  142.250.80.46
github.com  →  140.82.121.4
localhost   →  127.0.0.1
```

### How DNS Resolution Works

```
Browser cache → OS cache → Router cache → ISP DNS → Root DNS → TLD DNS → Authoritative DNS
```

1. Browser checks its own cache
2. OS checks its cache
3. Query goes to configured DNS resolver (usually your ISP)
4. Resolver queries root nameservers → `.com` nameservers → `google.com` nameservers
5. Answer is cached at every level for the TTL (Time To Live) period

### Exercise 1.1: Query DNS

Open your terminal and run:

```bash
# Look up the IP address of a domain
nslookup google.com

# More detailed query
dig google.com

# See the full resolution chain
dig +trace google.com
```

**Questions to answer:**
1. What IP address did `google.com` resolve to?
2. Did you get multiple IP addresses? Why might that be?
3. What is the TTL value? What does it mean?

---

## 1.4 The HTTP Protocol

HTTP (HyperText Transfer Protocol) is the language clients and servers speak. It is a **text-based**, **request-response** protocol.

### Anatomy of an HTTP Request

```
GET /api/users?page=2 HTTP/1.1        ← Request line (method, path, version)
Host: api.example.com                  ← Required header
Accept: application/json               ← What format client wants
Authorization: Bearer eyJhbGc...       ← Authentication token
User-Agent: curl/7.88.1               ← Client identification
                                       ← Empty line (separates headers from body)
                                       ← No body for GET requests
```

### Anatomy of an HTTP Response

```
HTTP/1.1 200 OK                        ← Status line (version, code, reason)
Content-Type: application/json         ← What format the body is in
Content-Length: 245                     ← Size of body in bytes
Cache-Control: max-age=3600            ← Caching instructions
                                       ← Empty line
{                                      ← Response body
  "users": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ],
  "page": 2,
  "total_pages": 5
}
```

### HTTP Methods

| Method | Purpose | Has Body? | Idempotent? | Safe? |
|--------|---------|-----------|-------------|-------|
| GET | Retrieve a resource | No | Yes | Yes |
| POST | Create a resource | Yes | No | No |
| PUT | Replace a resource entirely | Yes | Yes | No |
| PATCH | Partially update a resource | Yes | No* | No |
| DELETE | Remove a resource | Rarely | Yes | No |
| HEAD | GET without body (metadata only) | No | Yes | Yes |
| OPTIONS | What methods are allowed? | No | Yes | Yes |

**Idempotent** = calling it multiple times produces the same result as calling it once.
**Safe** = does not modify server state.

*PATCH can be made idempotent depending on implementation.

### HTTP Status Codes

Memorize these categories:

| Range | Category | Meaning |
|-------|----------|---------|
| 1xx | Informational | Request received, processing |
| 2xx | Success | Request succeeded |
| 3xx | Redirection | Further action needed |
| 4xx | Client Error | You messed up |
| 5xx | Server Error | Server messed up |

**Must-know codes:**

```
200 OK              – Success
201 Created         – Resource created (after POST)
204 No Content      – Success, nothing to return (after DELETE)
301 Moved Permanently – Resource URL changed permanently
304 Not Modified    – Cached version is still valid
400 Bad Request     – Malformed request
401 Unauthorized    – Not authenticated (should be "Unauthenticated")
403 Forbidden       – Authenticated but not authorized
404 Not Found       – Resource doesn't exist
405 Method Not Allowed – Wrong HTTP method
409 Conflict        – State conflict (e.g., duplicate resource)
422 Unprocessable Entity – Valid syntax but semantic errors
429 Too Many Requests – Rate limited
500 Internal Server Error – Generic server failure
502 Bad Gateway     – Upstream server error
503 Service Unavailable – Server overloaded or in maintenance
504 Gateway Timeout – Upstream server didn't respond in time
```

### Exercise 1.2: Read Real HTTP Traffic

```bash
# Make a request and see the full HTTP exchange
curl -v https://httpbin.org/get

# See just the response headers
curl -I https://httpbin.org/get

# Make a POST request with a body
curl -v -X POST https://httpbin.org/post \
  -H "Content-Type: application/json" \
  -d '{"name": "Alice", "age": 30}'
```

**Study the output.** Identify:
1. The request line
2. The request headers
3. The status line
4. The response headers
5. The response body

---

## 1.5 HTTP Headers

Headers are key-value metadata attached to requests and responses. They control caching, authentication, content negotiation, and more.

### Essential Request Headers

| Header | Purpose | Example |
|--------|---------|---------|
| `Host` | Target server | `Host: api.example.com` |
| `Accept` | Desired response format | `Accept: application/json` |
| `Content-Type` | Format of request body | `Content-Type: application/json` |
| `Authorization` | Authentication credentials | `Authorization: Bearer <token>` |
| `User-Agent` | Client identification | `User-Agent: MyApp/1.0` |
| `Accept-Encoding` | Compression support | `Accept-Encoding: gzip, deflate` |

### Essential Response Headers

| Header | Purpose | Example |
|--------|---------|---------|
| `Content-Type` | Format of response body | `Content-Type: application/json` |
| `Content-Length` | Body size in bytes | `Content-Length: 1234` |
| `Cache-Control` | Caching rules | `Cache-Control: max-age=3600` |
| `Set-Cookie` | Set a cookie on client | `Set-Cookie: session=abc123` |
| `Location` | Redirect target | `Location: /api/users/42` |
| `X-Request-Id` | Request tracking | `X-Request-Id: uuid-here` |

---

## 1.6 JSON — The Language of Web APIs

JSON (JavaScript Object Notation) is the dominant data format for web APIs. It is text-based, human-readable, and language-agnostic.

### JSON Syntax

```json
{
  "string": "hello",
  "number": 42,
  "float": 3.14,
  "boolean": true,
  "null_value": null,
  "array": [1, 2, 3],
  "nested_object": {
    "key": "value"
  }
}
```

### Rules

- Keys must be double-quoted strings
- No trailing commas
- No comments
- No single quotes
- No `undefined` (use `null`)

### JSON in Python

```python
import json

# Python dict → JSON string
data = {"name": "Alice", "age": 30, "active": True}
json_string = json.dumps(data, indent=2)
print(json_string)

# JSON string → Python dict
parsed = json.loads('{"name": "Bob", "age": 25}')
print(parsed["name"])  # "Bob"
```

### Exercise 1.3: Work with JSON

```bash
# Fetch JSON from an API
curl -s https://jsonplaceholder.typicode.com/users/1 | python3 -m json.tool

# Create a file with JSON
echo '{"name": "test", "version": "1.0"}' | python3 -m json.tool > test.json

# Parse JSON with Python
python3 -c "
import json, urllib.request
data = urllib.request.urlopen('https://jsonplaceholder.typicode.com/todos/1').read()
todo = json.loads(data)
print(f'Title: {todo[\"title\"]}')
print(f'Completed: {todo[\"completed\"]}')
"
```

---

## 1.7 Statelessness

HTTP is **stateless**. This is one of the most important concepts in web development.

### What Statelessness Means

Each HTTP request is independent. The server does not remember previous requests. Every request must contain all the information the server needs to process it.

### Analogy

Imagine calling a help desk where the agent has amnesia. Every time you call, you must:
1. Identify yourself again
2. Explain your problem from scratch
3. Provide all relevant context

This is HTTP. Every. Single. Request.

### Why Statelessness Matters

**Advantages:**
- Servers can be scaled horizontally (any server can handle any request)
- No server-side session memory needed
- Simpler server implementation
- Better fault tolerance

**Consequences:**
- Authentication tokens must be sent with every request
- Shopping carts need to be stored somewhere (database, cookies, or client)
- "Sessions" are an abstraction layer on top of stateless HTTP

### How State Is Maintained Despite Statelessness

```
┌─────────┐                          ┌─────────┐
│ Client  │   Request + Auth Token   │ Server  │
│         │ ───────────────────────► │         │
│ (stores │                          │ (looks  │
│  token) │   Response + Data        │  up     │
│         │ ◄─────────────────────── │  token) │
└─────────┘                          └─────────┘
```

Common mechanisms:
- **Cookies**: Server sets, browser sends automatically
- **Tokens**: Client stores, sends in `Authorization` header
- **URL parameters**: State encoded in URL (limited, avoid for sensitive data)

---

## 1.8 Content Negotiation

Content negotiation is how client and server agree on data format.

```
Client: "I want JSON"     →  Accept: application/json
Server: "Here's JSON"     →  Content-Type: application/json

Client: "I want XML"      →  Accept: application/xml
Server: "Here's XML"      →  Content-Type: application/xml

Client: "I want anything" →  Accept: */*
Server: "Here's my default" → Content-Type: application/json
```

Most modern APIs only support JSON. But the mechanism exists and you will encounter it.

---

## Checkpoint Quiz

Answer these without looking back. If you cannot, re-read the relevant section.

1. What layer of the network stack does HTTP operate on?
2. What does DNS do? Why is it necessary?
3. What are the three parts of an HTTP request line?
4. What is the difference between a 401 and a 403 status code?
5. Why is HTTP called stateless? What are two consequences?
6. What Content-Type header would you set when sending JSON?
7. What does idempotent mean? Which HTTP methods are idempotent?
8. What happens if you send a GET request with a request body?
9. Name three things that happen between typing a URL and seeing a page.
10. Why are there multiple IP addresses for google.com?

---

## Common Mistakes

1. **Confusing 401 and 403.** 401 means "I don't know who you are." 403 means "I know who you are, and you're not allowed."
2. **Thinking HTTP remembers you.** It does not. Tokens and cookies create the illusion of memory.
3. **Ignoring status codes.** Many beginners only check if a response "looks right." Status codes are the first thing to check.
4. **Assuming JSON is the only format.** It dominates, but XML, Protocol Buffers, MessagePack, and others exist.
5. **Not understanding that HTTPS is just HTTP + TLS.** The protocol is the same. The encryption wraps it.

---

## Mini Project: HTTP Explorer

Build a Python script that:

1. Takes a URL as a command-line argument
2. Makes a GET request to that URL
3. Prints the status code, all response headers (formatted), and the body (pretty-printed if JSON)

```python
# http_explorer.py
import sys
import json
import urllib.request
import urllib.error

def explore(url):
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "HTTPExplorer/1.0"})
        with urllib.request.urlopen(req) as response:
            print(f"Status: {response.status} {response.reason}")
            print(f"\n--- Headers ---")
            for key, value in response.headers.items():
                print(f"  {key}: {value}")

            body = response.read().decode("utf-8")
            print(f"\n--- Body ---")
            try:
                parsed = json.loads(body)
                print(json.dumps(parsed, indent=2))
            except json.JSONDecodeError:
                print(body[:500])

    except urllib.error.HTTPError as e:
        print(f"HTTP Error: {e.code} {e.reason}")
    except urllib.error.URLError as e:
        print(f"URL Error: {e.reason}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python http_explorer.py <url>")
        sys.exit(1)
    explore(sys.argv[1])
```

**Test it:**
```bash
python3 http_explorer.py https://httpbin.org/get
python3 http_explorer.py https://jsonplaceholder.typicode.com/posts/1
python3 http_explorer.py https://httpbin.org/status/404
```

---

## Next Module

Proceed to `02_servers_and_networking.md` →
