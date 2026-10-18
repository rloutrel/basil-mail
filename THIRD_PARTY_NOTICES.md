# Third-party notices

Basil — mail management component is MIT-licensed. It depends on the following
permissively licensed third-party packages:

| Package | License | Notes |
|---|---|---|
| Django | BSD-3-Clause | Web framework, ORM, admin |
| psycopg2-binary | LGPL-3.0 (runtime dependency only, not distributed) | PostgreSQL adapter — Django's documented PostgreSQL driver; see note below |

Frontend assets loaded at runtime (not distributed with this repository):

| Asset | License |
|---|---|
| HTMX | BSD-2-Clause |
| Alpine.js | MIT |
| Bootstrap Icons (vendored SVGs in `static/icons/`) | MIT |

Everything else is the Python standard library (`imaplib`, `email`).

**Note on psycopg2-binary:** it is licensed under LGPL-3.0, but it is used
strictly as an unmodified runtime dependency (installed from PyPI, never
distributed with this project) and is not linked statically — the LGPL
explicitly permits this. If you prefer a fully permissive stack, install the
Apache-2.0-licensed `psycopg` package instead; Django 5 supports it natively
(`pip install "psycopg[binary]"` and no other change is needed).
