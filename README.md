# sec-task-2 — RBAC Design Extensions

This folder is an **exploratory extension** built on top of the
original RBAC implementation. It begins as a copy of the working
project and gradually evolves it with additional capabilities,
alternative storage backends, and architectural enhancements that
commonly arise as an RBAC system grows.

The objective is to explore how a simple RBAC service can evolve while
keeping the same layered architecture (`routes → service → storage`)
and maintaining clear separation of concerns.

---

## Table of Contents

1. Purpose & Difference from the Original
2. What's New
3. Folder Structure
4. Installation
5. Running the Extended In-Memory Version
6. Running the SQL Version
7. Running the Advanced Version
8. Running the Tests
9. API Additions
10. Design Notes

---

## Purpose & Difference from the Original

| | Original (`ambsec-task/`) | This folder (`sec-task-2/`) |
|---|---|---|
| Goal | Minimal RBAC implementation | Exploratory evolution of the same design |
| Storage | In-memory only | In-memory and a parallel SQLite implementation |
| Features | Core RBAC | Additional APIs, validation, caching, audit logging, utility endpoints, and architectural enhancements |
| Errors | `{"detail": ...}` | Centralized `{"error": {"code","message"}}` responses |
| Validation | Basic | Input normalization, duplicate prevention, stronger validation |
| Documentation | README + report | Additional implementation notes and scalability documentation |

The architecture intentionally remains identical to the original project.
Every request still flows through

```
routes → service → storage
```

Only the capabilities evolve. Because the storage layer remains isolated,
the same service logic can operate on either the in-memory implementation
or the SQLite-backed implementation with minimal changes.

---

## What's New

### Part 1 — Extended RBAC functionality (in-memory)

Adds practical RBAC capabilities including:

- delete user / role (with cascade)
- get by id
- rename (PATCH)
- replace roles and permissions (PUT)
- effective permission computation
- search endpoints
- users belonging to a role
- duplicate prevention
- centralized error handling
- stronger validation and normalization

---

### Part 2 — Operational additions

Introduces several operational features:

- created_at / updated_at timestamps
- audit logging
- `/health`
- `/system/info`
- `/system/audit`
- `/users/count`
- `/roles/count`
- effective permission caching with cache invalidation

---

### Part 3 — SQLite implementation

A second implementation backed by the Python standard library's
`sqlite3` module.

The API surface remains the same while the storage layer is replaced
with relational tables and parameterized SQL queries, demonstrating how
the service layer remains reusable across different persistence
implementations.

---

### Part 4 — Advanced extensions

A separate implementation exploring additional RBAC capabilities:

- OAuth2 password authentication using JWT
- multi-tenancy
- role hierarchy and inherited permissions
- permission-protected management APIs

These features are intentionally isolated so they can be understood
independently of the core implementation.

---

### Part 5 — Scalability notes

`docs/scalability-evolution.md` discusses how the project could evolve
from an in-memory prototype toward larger production deployments,
covering topics such as indexing, caching, transactions, pooling,
replication, hierarchy, audit logging, and versioning.

---

## Design Philosophy

Rather than redesigning the project from scratch, this repository
incrementally extends the original implementation while preserving its
layered architecture.

Each extension is intended to answer a practical design question such as:

- What additional APIs become useful over time?
- How can validation become more robust?
- How should permission computation be cached?
- How easily can the storage backend be replaced?
- What changes are required to introduce authentication?
- How can tenant isolation be incorporated without changing the overall architecture?

The result is a collection of progressively more capable RBAC
implementations that explore different architectural directions while
sharing the same core design principles.
