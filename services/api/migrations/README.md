# Database migrations

Alembic migrations are the canonical production schema history.

```bash
make migrate
```

Docker runs `alembic upgrade head` before starting the API. The application also
creates missing tables on startup so SQLite remains a zero-setup local and test
fallback; production changes must still include a migration.

Current revisions:

- `0001_durable_matches` creates durable matches, moves, and events.
- `0002_authoritative_clocks` adds time-control settings, remaining balances,
  active-turn anchors, timeout results, and per-move clock balances.
