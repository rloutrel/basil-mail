# Basil — Mail

Basil (Basil — Assistant Synthétique à Intelligence Libre; English: Synthetic
Assistant with Free Intelligence) is a personal platform combining several
standalone components. This repository is the **email management component**:
a general-purpose, rule-based mail collector and organizer. Rules and sources
are domain-agnostic — job offers, personal mail, newsletters, anything.

The current phase is rule-based only; AI-powered features (rules and
classification) will be introduced later (see [Roadmap](#roadmap)).

It is a standalone Django project, fully self-contained and runnable on its
own.

## Features

- **Mail sources**: any IMAP mailbox (SSL/TLS or plain), per-source fetch
  frequency, enable/disable, inline "Test connection" (IMAP login + select
  INBOX, no page reload).
- **Rule-based sorting**: rules match a target field (sender, subject or
  body) with either an exact match or a regular expression (validated
  inline). Every matching rule is recorded per mail; mails matching no rule
  are "Unsorted" and still stored and listed.
- **Mails page**: daily-use list with pagination, color-coded matched vs.
  unsorted mails (with badges, not color alone), clickable rule badges that
  filter the list, an overlay showing the body with the first extracted
  `http(s)` link clickable, and a non-blocking "Fetch now" button.
- **Filters** (AND logic, preserved across pagination, state kept in the URL
  querystring): by rule (including "Unsorted"), by source mailbox, by sender
  (contains, case-insensitive), by subject keywords (contains,
  case-insensitive). Filtering happens through HTMX without a full page
  reload.
- **Strict collector constraint**: the collector never alters mail state on
  the IMAP server — it uses `BODY.PEEK`, never marks messages as seen, and
  never moves or deletes anything.
- **Dark / light theme**: toggle in the navbar, persisted in `localStorage`,
  defaulting to `prefers-color-scheme`.
- **Django admin** for debugging.

## Installation

### With Docker (recommended)

Requirements: Docker and Docker Compose.

```bash
git clone https://github.com/rloutrel/basil-mail.git
cd basil-mail
cp .env.example .env        # edit DJANGO_SECRET_KEY and credentials
docker compose up --build -d
```

The entrypoint runs migrations and `collectstatic` automatically, then starts
the server. The application is available at
[http://localhost:8000](http://localhost:8000). PostgreSQL data is persisted
in the `postgres_data` named volume.

#### Port configuration

The published host port is configurable with the `WEB_PORT` environment
variable (default `8000`):

```bash
WEB_PORT=8080 docker compose up -d   # -> http://localhost:8080
```

To publish **nothing** on the host — e.g. when running behind a reverse
proxy (nginx) on an internal Docker network — apply the
`docker-compose.no-ports.yml` override (Docker Compose v2.24+):

```bash
docker compose -f docker-compose.yml -f docker-compose.no-ports.yml up -d
# or
COMPOSE_FILE=docker-compose.yml:docker-compose.no-ports.yml docker compose up -d
```

In that case, set `DJANGO_ALLOWED_HOSTS` to your proxy's host name(s).

### Without Docker

Requirements: Python 3.12+, a PostgreSQL server.

```bash
git clone https://github.com/rloutrel/basil-mail.git
cd basil-mail
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # point POSTGRES_* (or DATABASE_URL) at your server
set -a; source .env; set +a # or export the variables manually
python manage.py migrate
python manage.py collectstatic
python manage.py runserver
```

### Fixtures

Load a demo source and two example rules (a job-offer rule and a personal
mail rule):

```bash
python manage.py loaddata initial_data        # non-Docker
docker compose exec web python manage.py loaddata initial_data  # Docker
```

### Creating a superuser (admin)

```bash
python manage.py createsuperuser             # non-Docker
docker compose exec web python manage.py createsuperuser  # Docker
```

The admin is available at [http://localhost:8000/admin/](http://localhost:8000/admin/).

## Configuring sources

On the **Configuration** page, add a source with its IMAP host, port,
SSL/TLS flag, username and password, mailbox folder (default `INBOX`), and a
fetch frequency in minutes. Use the **Test connection** button on each source
card: it performs a real IMAP login and a read-only `SELECT INBOX`, and shows
the result inline (no page reload). The fetch only reads (`BODY.PEEK`); your
mailbox is never modified.

## Collecting mails (cron)

The `fetch_mails` management command fetches, for each enabled source whose
interval has elapsed, all messages not yet stored (deduplicated by
`Message-ID` per source), applies the enabled rules and records the matches.

Cron line (non-Docker, every 5 minutes):

```cron
*/5 * * * * cd /path/to/basil-mail && set -a && . ./.env && set +a && /path/to/venv/bin/python manage.py fetch_mails >> /var/log/basil-mail.log 2>&1
```

Docker Compose variant:

```cron
*/5 * * * * cd /path/to/basil-mail && docker compose exec -T web python manage.py fetch_mails >> /var/log/basil-mail.log 2>&1
```

You can also trigger a fetch from the Mails page with the **Fetch now**
button (it runs in the background and does not block the request), or run the
command manually for a single source:

```bash
python manage.py fetch_mails --source "Personal mailbox"
```

## Testing

The suite covers model constraints (unique `message_id` per source), rule
matching (exact and regex, several rules per mail), regex validation, filter
combinations, and fetch logic against a mocked IMAP server. IMAP interactions
are always mocked — no test ever talks to a real server. The suite runs
against PostgreSQL (there is no SQLite fallback).

Non-Docker:

```bash
export POSTGRES_HOST=localhost POSTGRES_DB=basil_mail POSTGRES_USER=basil POSTGRES_PASSWORD=basil
python manage.py test
```

Docker:

```bash
docker compose exec web python manage.py test
```

## Languages

The interface is internationalised and ships with English, German and
French (`django.po` files under `locale/`). The language is chosen by
these standards, in order:

1. the user's explicit choice via the language dropdown (stored in the
   Django session cookie and mirrored in `localStorage` under
   `basil-language`),
2. otherwise the browser's `Accept-Language` header (standard HTTP
   content negotiation, as implemented by Django's `LocaleMiddleware`),
3. otherwise the default (`LANGUAGE_CODE = en-gb`).

To maintain translations, update the `.po` files and run:

```bash
python manage.py compilemessages       # non-Docker
docker compose exec web python manage.py compilemessages  # Docker
```

## Theming

The UI ships with complete light and dark themes built on CSS custom
properties. The toggle in the navbar switches themes, persists the choice in
`localStorage` (`basil-theme`), and defaults to the operating-system
preference (`prefers-color-scheme`).

## Basil ecosystem

This component is part of the Basil ecosystem, alongside other Basil
components (assistant, notes, etc.). It is fully standalone, but its
architecture is intentionally open for later integration.

## Roadmap

- Simple actions on mails: delete (local only), forward.
- Complex actions: extract content and forward to other Basil components
  (message queue or REST client).
- AI-powered rules and classification.

## License

MIT — see [LICENSE](LICENSE). Third-party dependencies and their licenses are
listed in [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
