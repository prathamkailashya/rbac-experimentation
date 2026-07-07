# sec-task-2 — RBAC Interview Playground

This folder is an **interview-preparation playground** built on top of the
original RBAC take-home (in the sibling `ambsec-task/` folder). It starts as a
copy of that working project and extends it to answer the questions interviewers
actually ask next: *"now add one more feature"*, *"how would you change this?"*,
*"what if we used a database?"*, *"how does this scale?"*.

> The original `ambsec-task/` is the **submission version** and is left
> completely untouched. Everything here is additive.

---

## Table of Contents

1. [Purpose & Difference from the Original](#purpose--difference-from-the-original)
2. [What's New](#whats-new)
3. [Folder Structure](#folder-structure)
4. [Installation](#installation)
5. [Running the Extended In-Memory Version](#running-the-extended-in-memory-version)
6. [Running the SQL Version](#running-the-sql-version)
7. [Running the Tests](#running-the-tests)
8. [API Additions](#api-additions)
9. [How to Study from the Report & Docs](#how-to-study-from-the-report--docs)
10. [Design Notes](#design-notes)

---

## Purpose & Difference from the Original

| | Original (`ambsec-task/`) | This folder (`sec-task-2/`) |
|---|---|---|
| Goal | Clean, submission-ready take-home | Practice extending it under interview pressure |
| Storage | In-memory only | In-memory **and** a parallel SQLite version (stdlib `sqlite3`) |
| Features | Core RBAC + delete | + rename, replace, search, effective permissions, counts, audit, health, etc. |
| Errors | `{"detail": ...}` | Centralized `{"error": {"code", "message"}}` |
| Validation | Minimal | Trim, reject blanks, normalize, duplicate prevention |
| Docs | README + `report.tex` | + `feature_extensions_report.tex` + scalability doc |

The **architecture is identical** to the original: every feature goes through
`routes → service → storage`. The service never imports FastAPI; storage stays a
swappable layer (which is exactly why the SQL version reuses the same logic).

## What's New

**Part 1 — follow-up features (in-memory `app/`):**
delete user/role (with cascade), get-by-id, rename (PATCH), replace roles/permissions
(PUT), effective permissions, users-having-a-role, search users/roles, duplicate
prevention, trimming/normalization, and centralized error responses.

**Part 2 — operability bonuses:**
`created_at`/`updated_at` timestamps, an in-memory audit log, `/health`,
`/system/info`, `/system/audit`, `/users/count`, `/roles/count`, and a per-user
effective-permission **cache** with invalidation.

**Part 3 — SQL version (`sql_version/`):**
the same API implemented with the standard library's **`sqlite3` module + SQLite**
(no ORM), showing real tables, primary/foreign keys, and the two many-to-many
join tables (`user_roles`, `role_permissions`). Every query is plain,
parameterized SQL — the permission check is a single readable JOIN. The business
logic mirrors the in-memory version; only the storage calls change.

**Part 3b — advanced version (`advanced/`, in-memory):**
a small, self-contained app that layers three commonly-asked features on top of
the core: **OAuth2 password login (JWT)**, **multi-tenancy** (all data scoped per
tenant), and **role hierarchy** (a role inherits its parents' permissions). It
also shows RBAC guarding its *own* API (write endpoints require `roles:write` /
`users:write`). Kept deliberately small so every line is explainable.

**Part 4 — scalability doc:** `docs/scalability-evolution.md`.

**Part 5 — study guide:** `feature_extensions_report.tex`.

## Folder Structure

```
sec-task-2/
├── app/                     # Extended IN-MEMORY backend
│   ├── models.py            # dataclasses + timestamps
│   ├── storage.py           # dicts + audit_log + permission_cache
│   ├── services.py          # all rules (validation, cache, effective perms, ...)
│   ├── errors.py            # AppError / NotFound / Conflict / Validation
│   ├── schemas.py           # Pydantic request/response models
│   ├── routes.py            # endpoints (static paths before {id})
│   ├── dependencies.py      # get_service (DI)
│   ├── seed.py              # example data
│   └── main.py              # app, CORS, centralized error handlers, static mount
├── sql_version/             # stdlib SQLITE3 backend (same API, no ORM)
│   ├── app/
│   │   ├── db.py            # connection factory, schema (DDL), get_db
│   │   ├── models.py        # plain dataclasses for rows read back
│   │   ├── services.py      # same rules, storage via a sqlite3 Connection
│   │   ├── routes.py        # endpoints depending on get_db
│   │   ├── schemas.py, errors.py, seed.py, main.py
│   └── tests/test_sql.py
├── advanced/                # OAuth + multi-tenancy + role hierarchy (in-memory)
│   ├── app/
│   │   ├── auth.py          # password hashing (PBKDF2) + JWT helpers
│   │   ├── models.py        # + tenant_id, parent_ids, password_hash
│   │   ├── services.py      # tenant-scoped rules + hierarchy effective perms
│   │   ├── dependencies.py  # get_current_user + require_permission guards
│   │   ├── routes.py        # /token, /me, tenant-scoped RBAC endpoints
│   │   ├── storage.py, schemas.py, errors.py, seed.py, main.py
│   └── tests/test_advanced.py
├── frontend/                # shared demo UI (served by whichever backend runs)
├── tests/
│   ├── test_rbac.py         # original tests (still pass)
│   └── test_extensions.py   # tests for the new features
├── docs/scalability-evolution.md
├── feature_extensions_report.tex
├── requirements.txt, pyproject.toml, README.md, report.tex (copied)
```

## Installation

Requires **Python 3.11+**.

```bash
cd sec-task-2
python3 -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

## Running the Extended In-Memory Version

```bash
uvicorn app.main:app --reload
```

- API + docs: `http://127.0.0.1:8000` and `http://127.0.0.1:8000/docs`
- Frontend: open `http://127.0.0.1:8000/`
- Seeded with Alice / Bob / Charlie and admin / editor / viewer.

## Running the SQL Version

Run **one** backend at a time (both use port 8000; the frontend targets whatever
origin served it).

```bash
uvicorn sql_version.app.main:app --reload
```

On first run it creates `sql_version/rbac.db` (SQLite, gitignored) and seeds the
same example data. Same URLs, same responses as the in-memory version.

## Running the Advanced Version (OAuth + multi-tenant + hierarchy)

```bash
uvicorn advanced.app.main:app --reload
```

API-only (no frontend). Try it against the seeded data — two tenants (`acme`,
`globex`) with a role hierarchy `admin → editor → viewer`:

```bash
# 1) log in (OAuth2 password flow) -> get a JWT
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/token \
  -d 'username=alice&password=alice-pw' | python3 -c 'import sys,json;print(json.load(sys.stdin)["access_token"])')

# 2) see your identity + effective permissions (documents:read is INHERITED)
curl -s http://127.0.0.1:8000/me -H "Authorization: Bearer $TOKEN"

# 3) tenant-scoped: alice (acme) sees admin/editor/viewer; carol (globex) sees only gviewer
curl -s http://127.0.0.1:8000/roles -H "Authorization: Bearer $TOKEN"
```

Seeded logins: `alice`/`alice-pw` (acme admin), `bob`/`bob-pw` (acme editor),
`carol`/`carol-pw` (globex viewer). Write endpoints require `roles:write` /
`users:write`, so `bob` gets **403** creating a role while `alice` gets **201**.

**How the three features fit together (the key idea):** the JWT carries both the
user id *and* the tenant, so one `get_current_user` dependency gives you identity
and scope at once; the service filters every query by that tenant; and the
permission check simply computes the effective set over the role hierarchy
(`admin → editor → viewer`) before testing membership. The check itself is
unchanged — only *how the effective set is built* now includes inheritance.

## Running the Tests

```bash
pytest                    # runs tests/ AND sql_version/tests/
```

- `tests/test_rbac.py` — the original suite (unchanged behavior).
- `tests/test_extensions.py` — new in-memory features.
- `sql_version/tests/test_sql.py` — the SQL version (fresh temp-file SQLite per test).

All tests pass. Each new feature has success, failure, edge, duplicate, and
validation coverage.

## API Additions

Beyond the original endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/users/{id}` | Get one user |
| PATCH | `/users/{id}` | Rename user |
| PUT | `/users/{id}/roles` | Replace a user's roles |
| GET | `/users/{id}/permissions` | Effective (merged) permissions |
| GET | `/users?name=` | Search users |
| GET | `/users/count` | User count |
| GET | `/roles/{id}` | Get one role |
| PATCH | `/roles/{id}` | Rename role |
| PUT | `/roles/{id}/permissions` | Replace a role's permissions |
| GET | `/roles/{id}/users` | Users having this role |
| GET | `/roles?name=` | Search roles |
| GET | `/roles/count` | Role count |
| GET | `/health` | Liveness |
| GET | `/system/info` | Name, version, counts |
| GET | `/system/audit?limit=` | Recent operations (in-memory version) |

Errors are consistent: `{"error": {"code": "not_found", "message": "..."}}`
(404), `conflict` (409, duplicate names), `validation_error` (422, blank/invalid
input).

## How to Study from the Report & Docs

- **`feature_extensions_report.tex`** — the main study guide. Compile with
  `pdflatex feature_extensions_report.tex` (run twice for the table of contents).
  It covers: why interviewers ask follow-ups, a deep dive on every implemented
  feature, a repeatable **feature-design framework**, on-the-spot coding
  strategy, a **~150-feature catalog** (easy/medium/hard), a SQL migration guide,
  system-design evolution, memorization sheets, **75 mock questions**, and **~40
  whiteboard exercises**.
- **`docs/scalability-evolution.md`** — the in-memory → SQLite → PostgreSQL →
  production narrative (indexes, caching, pooling, transactions, concurrency,
  replicas, hierarchy, soft delete, audit, versioning).
- **`report.tex`** (copied from the original) — the foundational report on the
  core project; read it first if you are new to the codebase.

Suggested order: skim the original `report.tex` → read this README → read the
"Implemented Features" and "Feature Design Framework" chapters of
`feature_extensions_report.tex` → practice with the mock questions and whiteboard
exercises → read the scalability doc.

## Design Notes

- **Route ordering:** static paths (`/users/count`) are declared before
  parametrized ones (`/users/{user_id}`) so they are matched first.
- **All-or-nothing writes:** replace/bulk operations validate every referenced id
  before mutating, so a bad id never leaves a half-applied state.
- **Cache invalidation:** the effective-permission cache is invalidated on role
  and permission changes — there is a test that fails if invalidation is removed.
- **Normalization:** names are trimmed and must be unique (case-insensitive);
  permissions are lowercased so matching is predictable.
- **Storage seam:** compare `app/services.py` with `sql_version/app/services.py` —
  same rules, different storage. That contrast is the whole point of the layering.
# rbac-experimentation
