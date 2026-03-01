# Module 03: REST API Design

## Learning Objectives

By the end of this module, you will be able to:

- Define REST and its constraints
- Design resource-oriented APIs
- Choose correct HTTP methods for operations
- Structure URLs, path parameters, and query parameters properly
- Explain idempotency and why it matters
- Distinguish good API design from bad
- Version an API
- Design error responses

---

## 3.1 What Is REST?

REST (Representational State Transfer) is an **architectural style** for designing networked applications. It is not a protocol, not a standard, not a library. It is a set of constraints.

Roy Fielding defined REST in his 2000 doctoral dissertation. Most "REST APIs" on the internet violate at least some REST constraints. When people say "REST API," they usually mean "HTTP-based API that uses JSON and follows some conventions."

### The Six REST Constraints

| Constraint | Meaning |
|------------|---------|
| **Client-Server** | Client and server are separate. They evolve independently. |
| **Stateless** | Each request contains all info needed. No server-side sessions. |
| **Cacheable** | Responses must declare if they're cacheable. |
| **Uniform Interface** | Consistent URL structure, standard methods, self-descriptive messages. |
| **Layered System** | Client can't tell if it's connected directly to the server or through a proxy. |
| **Code on Demand** (optional) | Server can send executable code (JavaScript). Rarely used for APIs. |

The most practically important constraint is **Uniform Interface**. This is what makes REST APIs predictable.

---

## 3.2 Resources — The Core Concept

In REST, everything is a **resource**. A resource is a noun — a thing — that your API manages.

```
Users       → /users
Products    → /products
Orders      → /orders
Blog Posts  → /posts
Comments    → /comments
```

### Resources Are NOT Actions

```
WRONG (action-oriented):
  POST /createUser
  GET  /getUser?id=1
  POST /deleteUser
  POST /updateUserEmail

RIGHT (resource-oriented):
  POST   /users          → Create a user
  GET    /users/1        → Get user 1
  DELETE /users/1        → Delete user 1
  PATCH  /users/1        → Update user 1's fields
```

The HTTP method IS the verb. The URL IS the noun. Do not put verbs in URLs.

### Resource Hierarchy

Resources can be nested to show relationships:

```
GET  /users/42/orders          → All orders for user 42
GET  /users/42/orders/7        → Order 7 for user 42
POST /users/42/orders          → Create an order for user 42

GET  /posts/15/comments        → All comments on post 15
POST /posts/15/comments        → Add a comment to post 15
```

Rule of thumb: **nest at most 2 levels deep.** Beyond that, use query parameters or separate endpoints.

---

## 3.3 CRUD Operations

CRUD maps directly to HTTP methods:

| Operation | HTTP Method | URL Pattern | Status Code |
|-----------|-------------|-------------|-------------|
| **C**reate | POST | `/resources` | 201 Created |
| **R**ead (list) | GET | `/resources` | 200 OK |
| **R**ead (single) | GET | `/resources/{id}` | 200 OK |
| **U**pdate (full) | PUT | `/resources/{id}` | 200 OK |
| **U**pdate (partial) | PATCH | `/resources/{id}` | 200 OK |
| **D**elete | DELETE | `/resources/{id}` | 204 No Content |

### Example: Users API

```
POST   /users              → Create user
GET    /users              → List all users
GET    /users/42           → Get user 42
PUT    /users/42           → Replace user 42 entirely
PATCH  /users/42           → Update specific fields of user 42
DELETE /users/42           → Delete user 42
```

### PUT vs PATCH

**PUT** replaces the entire resource. You must send ALL fields.

```json
PUT /users/42
{
  "name": "Alice Updated",
  "email": "alice@new.com",
  "age": 31,
  "role": "admin"
}
```

**PATCH** updates specific fields. You send only what changed.

```json
PATCH /users/42
{
  "email": "alice@new.com"
}
```

Use PATCH for most updates. Use PUT only when replacement semantics are needed.

---

## 3.4 Path Parameters vs Query Parameters

### Path Parameters — Identify a specific resource

```
GET /users/42           → User with ID 42
GET /posts/15/comments  → Comments on post 15
GET /products/abc-123   → Product with slug "abc-123"
```

Path parameters are **required** and **identify** a resource.

### Query Parameters — Filter, sort, paginate, search

```
GET /users?role=admin                  → Filter by role
GET /users?sort=created_at&order=desc  → Sort by creation date
GET /users?page=2&limit=20            → Pagination
GET /users?search=alice               → Search
GET /products?min_price=10&max_price=50&category=electronics
```

Query parameters are **optional** and modify how you retrieve resources.

### Decision Framework

```
"Is this value needed to identify a specific resource?"
  YES → Path parameter:  /users/{id}
  NO  → "Is it filtering/modifying a collection?"
    YES → Query parameter:  /users?role=admin
    NO  → "Is it data for creating/updating?"
      YES → Request body (JSON)
```

---

## 3.5 Request and Response Bodies

### Request Body (for POST, PUT, PATCH)

```json
POST /users
Content-Type: application/json

{
  "name": "Alice",
  "email": "alice@example.com",
  "password": "securepassword123"
}
```

### Response Body

Successful creation:
```json
HTTP/1.1 201 Created
Location: /users/42
Content-Type: application/json

{
  "id": 42,
  "name": "Alice",
  "email": "alice@example.com",
  "created_at": "2025-01-15T10:30:00Z"
}
```

Note: **Never echo back passwords or sensitive data.**

### Collection Response (with pagination)

```json
HTTP/1.1 200 OK
Content-Type: application/json

{
  "data": [
    {"id": 1, "name": "Alice"},
    {"id": 2, "name": "Bob"}
  ],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 47,
    "total_pages": 3
  }
}
```

---

## 3.6 Idempotency

An operation is **idempotent** if performing it multiple times has the same effect as performing it once.

```
GET  /users/42        → Always returns user 42. Idempotent. ✓
PUT  /users/42        → Always sets user 42 to this state. Idempotent. ✓
DELETE /users/42      → First call deletes. Second call: already gone. Same end state. Idempotent. ✓
POST /users           → Each call creates a NEW user. NOT idempotent. ✗
```

### Why Idempotency Matters

Network requests fail. They time out. They get retried. If a request is idempotent, retrying is safe. If it is not (POST), retrying might create duplicates.

```
Scenario: Client sends POST /orders. Network times out.
Did the server receive it? Did the order get created?
Client doesn't know.
If client retries, and the first request DID succeed → duplicate order.
```

Solutions for non-idempotent operations:
1. **Idempotency keys**: Client sends a unique key. Server deduplicates.
2. **Check-then-create**: Client checks if resource exists before creating.

```
POST /orders
Idempotency-Key: 550e8400-e29b-41d4-a716-446655440000

Server: "I've seen this key before → return existing order"
```

---

## 3.7 Error Responses

Errors should be structured, consistent, and helpful.

### Good Error Response Format

```json
HTTP/1.1 422 Unprocessable Entity
Content-Type: application/json

{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Request validation failed",
    "details": [
      {
        "field": "email",
        "message": "Not a valid email address",
        "value": "not-an-email"
      },
      {
        "field": "age",
        "message": "Must be a positive integer",
        "value": -5
      }
    ]
  }
}
```

### Error Response Rules

1. Always return JSON (not HTML error pages)
2. Use appropriate status codes (don't use 200 for errors)
3. Include a machine-readable error code
4. Include a human-readable message
5. Include field-level details for validation errors
6. Never expose stack traces or internal details in production

### Common Error Patterns

```json
// 400 Bad Request — malformed JSON, missing required header
{
  "error": {"code": "BAD_REQUEST", "message": "Invalid JSON in request body"}
}

// 401 Unauthorized — no token or invalid token
{
  "error": {"code": "UNAUTHORIZED", "message": "Authentication required"}
}

// 404 Not Found — resource doesn't exist
{
  "error": {"code": "NOT_FOUND", "message": "User with id 999 not found"}
}

// 409 Conflict — duplicate, state conflict
{
  "error": {"code": "CONFLICT", "message": "User with email alice@example.com already exists"}
}

// 429 Rate Limited
{
  "error": {"code": "RATE_LIMITED", "message": "Too many requests. Try again in 60 seconds."}
}
```

---

## 3.8 API Versioning

APIs evolve. Breaking changes need versioning.

### Strategy 1: URL Path Versioning (Most Common)

```
GET /v1/users
GET /v2/users
```

Pros: Clear, easy to implement, easy to route.
Cons: URL pollution.

### Strategy 2: Header Versioning

```
GET /users
Accept: application/vnd.myapi.v2+json
```

Pros: Clean URLs.
Cons: Harder to test, less visible.

### Strategy 3: Query Parameter

```
GET /users?version=2
```

Pros: Simple.
Cons: Messy.

**Recommendation: Use URL path versioning.** It is the most widely understood and easiest to work with.

### When to Version

- Removing a field from a response → breaking
- Renaming a field → breaking
- Changing a field's type → breaking
- Adding a new optional field to a response → NOT breaking
- Adding a new optional query parameter → NOT breaking

---

## 3.9 Good vs Bad API Design

### Bad API Design

```
POST /api/getUserById          ← Verb in URL, POST for read
GET  /api/users/delete/42      ← Side effect on GET
POST /api/createNewUser        ← Redundant verb
GET  /api/all-users-list       ← Weird naming
POST /api/users/42/makeAdmin   ← RPC-style, not resource-oriented

Response:
{
  "success": true,              ← Redundant (use status codes)
  "error_code": 0,              ← Magic number
  "data": { ... }
}
```

### Good API Design

```
GET    /api/v1/users           ← List users
POST   /api/v1/users           ← Create user
GET    /api/v1/users/42        ← Get user
PATCH  /api/v1/users/42        ← Update user
DELETE /api/v1/users/42        ← Delete user
PATCH  /api/v1/users/42/role   ← Update user role (sub-resource)

Response (success):
{
  "id": 42,
  "name": "Alice",
  "email": "alice@example.com",
  "role": "admin",
  "created_at": "2025-01-15T10:30:00Z"
}

Response (error):
HTTP/1.1 404 Not Found
{
  "error": {
    "code": "NOT_FOUND",
    "message": "User 42 not found"
  }
}
```

### API Design Checklist

- [ ] URLs use nouns, not verbs
- [ ] Plural nouns for collections (`/users`, not `/user`)
- [ ] HTTP methods match CRUD operations
- [ ] Consistent naming convention (snake_case or camelCase, pick one)
- [ ] Proper status codes for every response
- [ ] Structured error responses
- [ ] Pagination for list endpoints
- [ ] Versioning strategy defined
- [ ] No sensitive data in URLs (passwords, tokens)
- [ ] Filtering via query parameters, not body

---

## 3.10 Pagination

Every list endpoint must be paginated. Returning unbounded lists is a production incident waiting to happen.

### Offset-Based Pagination

```
GET /users?page=1&per_page=20

{
  "data": [...],
  "pagination": {
    "page": 1,
    "per_page": 20,
    "total": 150,
    "total_pages": 8,
    "next": "/users?page=2&per_page=20",
    "previous": null
  }
}
```

Pros: Simple, allows jumping to any page.
Cons: Inconsistent results if data changes between pages. Slow for large offsets.

### Cursor-Based Pagination

```
GET /users?limit=20&after=eyJpZCI6IDQyfQ==

{
  "data": [...],
  "pagination": {
    "has_more": true,
    "next_cursor": "eyJpZCI6IDYyfQ=="
  }
}
```

Pros: Consistent results, fast regardless of position.
Cons: Can't jump to arbitrary pages.

Use offset for simple cases. Use cursor for large datasets or real-time feeds.

---

## Exercises

### Exercise 3.1: Design an API

Design a complete REST API for a **Library Management System**. Define:

1. Resources (at least 4)
2. All CRUD endpoints for each resource
3. Path parameters and query parameters
4. Request and response bodies (JSON)
5. Error responses
6. Pagination strategy

Resources to consider: books, authors, members, loans, reservations.

### Exercise 3.2: Critique These APIs

For each endpoint, identify what's wrong and fix it:

```
1. GET  /api/getBooksByAuthor?author_id=5
2. POST /api/books/delete
3. GET  /api/books/42/getReviews
4. POST /api/addReviewToBook/42
5. PUT  /api/books/42  (with body: {"title": "New Title"})
```

### Exercise 3.3: Design Error Responses

Design appropriate error responses for:

1. User tries to borrow a book that's already checked out
2. User submits a review with rating = 11 (max is 5)
3. User tries to delete an author who has books in the system
4. Unauthenticated user tries to access admin endpoint
5. Request body is missing required "title" field

---

## Checkpoint Quiz

1. What are the six REST constraints?
2. Why should URLs contain nouns, not verbs?
3. What is the difference between PUT and PATCH?
4. When would you use a path parameter vs a query parameter?
5. What does idempotent mean? Give an example of a non-idempotent operation.
6. What status code should a successful DELETE return?
7. Why is `GET /users/delete/42` bad?
8. What are two strategies for API versioning?
9. Why must list endpoints be paginated?
10. What information should an error response contain?

---

## Common Mistakes

1. **Using POST for everything.** POST is for creation. Use the right method.
2. **Returning 200 for errors.** `200 OK { "error": "not found" }` is wrong. Use 404.
3. **Singular nouns.** Use `/users`, not `/user`.
4. **Inconsistent naming.** Pick `snake_case` or `camelCase` and stick with it.
5. **No pagination.** Your API works with 10 records. It falls over with 1 million.
6. **Putting sensitive data in URLs.** URLs get logged. Never put passwords or tokens in them.
7. **Deeply nested URLs.** `/users/42/orders/7/items/3/reviews` — too deep. Flatten it.
8. **Not using status codes.** Every response should have the correct status code.

---

## Real-World Mental Model

Think of a REST API as a **filing cabinet**:

```
Cabinet (API)
  ├── Drawer: /users          (collection)
  │     ├── Folder: /users/1  (individual resource)
  │     ├── Folder: /users/2
  │     └── Folder: /users/3
  │
  ├── Drawer: /products
  │     ├── Folder: /products/1
  │     └── Folder: /products/2
  │
  └── Drawer: /orders
        └── Folder: /orders/1
              └── Sub-folder: /orders/1/items  (nested resource)
```

- GET = Open drawer/folder and read
- POST = Add new folder to drawer
- PUT = Replace entire folder contents
- PATCH = Update one document in folder
- DELETE = Remove folder

---

## Next Module

Proceed to `04_linux_fundamentals.md` →
