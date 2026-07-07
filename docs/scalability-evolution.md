# Scalability Evolution: In-Memory → SQLite → PostgreSQL → Production

This document **explains** how the RBAC service evolves as load grows. Nothing
here is implemented in code — it is the "how would you scale this?" narrative to
walk an interviewer through. Both working implementations in this repo (the
in-memory `app/` and the stdlib-`sqlite3` `sql_version/`) are the first two rungs of
this ladder.

```
   In-Memory (dicts)  ->  SQLite (one file)  ->  PostgreSQL (a server)  ->  Production (many nodes + cache)
        stage 0                stage 1                  stage 2                        stage 3
```

The single reason this evolution is cheap: the **service layer is isolated from
storage**. Each rung mostly swaps the storage implementation while the business
rules and the HTTP contract stay the same.

---

## Stage 0 — In-Memory (the original submission)

- **What it is:** two Python dicts (`users`, `roles`) plus an effective-permission
  cache. Permission check is `O(R)` over a user's roles.
- **Good for:** demos, tests, a single process.
- **Limits:** data lost on restart; single process only (cannot scale
  horizontally because each process has its own memory); no durability, no
  transactions.
- **When to move on:** as soon as you need the data to survive a restart or be
  shared by more than one worker.

## Stage 1 — SQLite (this repo's `sql_version/`)

- **What changes:** storage becomes rows in a single file via the standard
  library's `sqlite3` module (plain, parameterized SQL — no ORM). Users, roles,
  and permissions are tables; the two many-to-many relationships become join
  tables (`user_roles`, `role_permissions`).
- **What you gain:** durability, real SQL queries and JOINs, constraints
  (unique names, unique `(resource, action)`), transactions per request.
- **Limits:** SQLite allows one writer at a time (writer lock); fine for low write
  concurrency and single-node apps, not for many concurrent writers.
- **Key point for interviews:** the `services.py` logic barely changed between
  Stage 0 and Stage 1 — only the storage calls did. That is the payoff of
  layering.

## Stage 2 — PostgreSQL

- **What changes:** swap the `sqlite3` calls for a Postgres driver (`psycopg`).
  The tables and the same-shaped SQL carry over; this is also the natural point
  to adopt a query builder or ORM (e.g. SQLAlchemy) if the hand-written SQL grows.
- **What you gain:** concurrent readers and writers (MVCC), robust indexing,
  server-side constraints and enforced foreign keys, mature tooling, replication.
- **What you add:** a **connection pool** so requests reuse connections instead
  of paying TCP + auth per call; **migrations** (e.g. Alembic) to evolve the
  schema safely.

## Stage 3 — Production (many nodes + cache + async)

- **Stateless API** behind a load balancer: because all state is in Postgres/Redis,
  you run N identical API instances and scale out horizontally.
- **Redis cache** for the read-hot path (permission checks): cache each user's
  effective permission set; a check becomes an `O(1)` cache hit.
- **Read replicas** for read-heavy traffic; writes go to the primary, reads fan
  out to replicas (accepting small replication lag).
- **Async workers / event bus** for cache invalidation, audit fan-out, and
  notifications.

---

## Cross-cutting concerns

### Indexes
- Index the columns you filter or join on: `users.name`, `roles.name`,
  `permissions(resource, action)`, and both join-table foreign keys.
- Indexes turn `O(n)` scans into `O(log n)` lookups; the cost is slightly slower
  writes and more storage. Index for your **actual** query patterns, not "just in
  case."
- In this repo the SQL schema already declares indexes on the name columns and a
  `UNIQUE(resource, action)` constraint (which is backed by an index).

### Caching
- **What to cache:** a user's effective permission set (the union of all their
  roles' permissions), keyed by user id.
- **Read path:** check cache → on miss, compute from the DB and store.
- **Invalidation** (the hard part):
  - user's roles change → invalidate that user;
  - a role's permissions change → invalidate **every** user holding that role
    (fan-out), or clear broadly;
  - a role is deleted → invalidate its holders.
- The in-memory version demonstrates this seam with `permission_cache` +
  `_invalidate_cache()`.

### Connection pooling
- Opening a DB connection is expensive (handshake + auth). A pool keeps a set of
  open connections and hands them out per request.
- Tune `pool_size` and `max_overflow` to the DB's connection limit and the number
  of API workers. Too many workers × too large a pool can exhaust the database.

### Transactions
- A transaction makes a group of writes atomic: all succeed or none do.
- Example: "replace a user's roles" should not leave the user half-updated if the
  second insert fails. With `sqlite3` this is one connection's transaction:
  several writes, then a single `commit()` (or `rollback()` on error).
- Keep transactions short to avoid holding locks.

### Concurrency & optimistic locking
- Two requests editing the same role can clash (lost update).
- **Optimistic locking:** add a `version` column; on update, `WHERE id = ? AND
  version = ?` and bump the version. If zero rows update, someone else changed it
  first — return `409 Conflict` and let the client retry.
- Preferred over pessimistic locking (SELECT ... FOR UPDATE) for read-heavy
  systems because it doesn't hold locks.

### Horizontal scaling
- The API is stateless once state lives in Postgres/Redis, so add instances
  behind a load balancer.
- Anything in process memory (like the Stage 0 cache) must move to a shared store
  (Redis) or instances will disagree.

### Read replicas
- Route reads (the vast majority — permission checks) to replicas and writes to
  the primary.
- Accept **eventual consistency**: a just-granted role may take a moment to appear
  on a replica. For authorization, decide whether that lag is acceptable or route
  security-critical reads to the primary.

### Role hierarchy & permission inheritance
- Let roles have parent roles (`admin` inherits `editor` inherits `viewer`).
- Effective permissions = union over the role and all its ancestors (transitive
  closure). Guard against cycles.
- Because it is expensive to compute per request, **precompute and cache** the
  closure, recomputing on hierarchy edits.

### Soft delete
- Instead of physically deleting, set `deleted_at` (or `is_active = false`) and
  filter it out of queries.
- Preserves history and audit trails and makes "undo" possible; the cost is that
  every query must exclude soft-deleted rows (a partial index helps).

### Audit logging
- Append-only record of who changed or checked what, and when (the in-memory
  version keeps a simple `audit_log`).
- In production, write audits to a durable, queryable store (a table, or a log
  pipeline). Never mutate audit rows.

### Versioning
- **API versioning:** prefix routes (`/v1`, `/v2`) or use headers so clients don't
  break when the contract changes; keep old versions until clients migrate.
- **Data/row versioning:** the `version` column above, and/or full history tables
  for "what did this role look like last month?"

---

## One-paragraph summary for an interview

"Today it's in-memory dicts with an `O(R)` check. The first move is a database —
SQLite to prove the storage swap, then PostgreSQL for real concurrency — keeping
the service layer unchanged thanks to the routes→service→storage split. Then I'd
put the read-hot permission check behind a Redis cache of each user's effective
permissions, invalidated on role/permission changes, run the stateless API on
several nodes behind a load balancer with read replicas, and add indexes on the
join keys and name columns. For correctness under concurrency I'd use short
transactions and optimistic locking with a `version` column, and for
operability, soft deletes, append-only audit logs, and API versioning."
