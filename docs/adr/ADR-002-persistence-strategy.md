# ADR-002: Persistence Strategy — SQLite Default with PostgreSQL-Ready Abstraction

## Context

The platform needs a relational store for the registry, deployment, and metrics domain model. It needs to be trivially runnable by a reviewer (`docker compose up`, no external DB provisioning) while still representing a realistic production data layer, since production-quality engineering is the explicit evaluation criterion.

## Decision

Use **SQLAlchemy 2.0 (async) as the single ORM/data-access layer**, with **SQLite as the default local/dev/demo database** and **PostgreSQL as the documented, config-driven production target**. No SQLite-specific or Postgres-specific SQL is written by hand; Alembic migrations are written against SQLAlchemy's generic types and validated to run cleanly on both.

## Rationale

- **Reviewer experience.** SQLite means `make run` / `docker compose up`
  produces a working system with zero external dependencies — no waiting on a Postgres container to become healthy, no connection-string fiddling.
- **The abstraction is the actual deliverable, not the database choice.**
  What's being evaluated is whether the persistence layer is designed correctly (repository pattern, migrations, indexing strategy) — that design is identical regardless of which engine backs it in a given
  environment.
- **Known SQLite limits are acceptable at this scale and are documented**
  (single-writer concurrency, weaker concurrent-transaction semantics, no native partitioning) — see `known-limitations.md`. None of the acceptance scenarios require concurrent-writer throughput beyond what
  SQLite provides.

## Consequences

- **Positive:** fast local setup; identical code path for dev and prod;
  Alembic migration discipline is exercised even in the take-home context.
- **Negative:** SQLite's single-writer model means the optimistic-concurrency check in Q2 is *less* necessary locally than it will be under concurrent writers in Postgres — the code still implements it correctly (version column, `409` on conflict) so behavior doesn't silently change at migration time; only the failure *frequency* differs.
- **Migration trigger:** any real multi-instance deployment, or the partitioning strategy requires Postgres — the swap is a `DATABASE_URL` change plus running the existing Alembic migrations against the new engine, not a rewrite.

## Rejected Alternative

**PostgreSQL-only from day one** — the correct production choice, and what `docker-compose.yml` also offers as an opt-in profile — but making it mandatory to even run the take-home locally adds friction disproportionate
to the benefit at this stage, and the abstraction being correct matters more here than which engine is behind it.
