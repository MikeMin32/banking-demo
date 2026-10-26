# Virtual Bank Account Manager

A private Telegram bot for tracking virtual bank accounts, manual balances, planned withdrawals, deposit instructions, and password-manager login references.

This is an **account tracking system**, not a bank. You type balances in by hand. The bot never logs into a bank, never scrapes a website, never talks to a banking API, and never sends a real transfer or withdrawal.

Creating or completing an expected withdrawal **does not** change the stored balance. Projected remaining is a display-only figure:

`projected remaining = current balance − pending expected withdrawals`

Currencies are **never** added together. USD, EUR, GBP and every other code stay in separate totals.

## Technology stack

- Python 3.12+
- [aiogram](https://docs.aiogram.dev/) 3.x (Telegram bot; no web frontend)
- aiosqlite (SQLite in WAL mode, foreign keys on)
- APScheduler 3.x
- pydantic-settings / python-dotenv
- pytest / pytest-asyncio
- Docker & Docker Compose

Money is stored as integer minor units (cents, etc.) and calculated with `Decimal`. Timestamps are UTC internally and converted with `zoneinfo` for display.

## Features

- Owner + optional allow-list authorization; private-chat only
- Dashboard with per-currency totals and projected remaining
- Account wizard using `VM {number} - {company}` names (Airwallex, N26, or a custom provider)
- Edit, archive, and delete accounts (with confirmation)
- Balance update, confirm-checked (timestamp only), history
- Expected withdrawals (pending / completed / cancelled)
- Deposit details with copy-friendly formatting
- Login URL / username / password-manager reference (never a bank password)
- Daily stale-balance reminders
- CSV exports that omit secrets and banking identifiers
- Online SQLite backup

## Local installation

### 1. Python virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Get a Telegram bot token from BotFather

1. Open Telegram and search for [@BotFather](https://t.me/BotFather).
2. Send `/newbot` and follow the prompts.
3. Copy the token. It looks like `123456789:AA...`.
4. Keep it private. Never commit it.

### 3. Find your Telegram user ID

The bot only talks to the owner (and optional extra IDs).

Easiest options:

- Message [@userinfobot](https://t.me/userinfobot) or [@getidsbot](https://t.me/getidsbot) and copy your numeric ID.
- Or start a throwaway bot, send it any message, and read `message.from.id` from [getUpdates](https://core.telegram.org/bots/api#getupdates).

### 4. Configure `.env`

```bash
cp .env.example .env
```

Fill in:

```
BOT_TOKEN=123456789:AA...
OWNER_TELEGRAM_ID=111111111
ALLOWED_USER_IDS=222222222,333333333
DATABASE_PATH=./data/bank_manager.db
TIMEZONE=Europe/Kyiv
REMINDER_TIME=09:00
LOG_LEVEL=INFO
```

| Variable | Required | Meaning |
|---|---|---|
| `BOT_TOKEN` | yes | Token from BotFather |
| `OWNER_TELEGRAM_ID` | yes | Your numeric Telegram user ID |
| `ALLOWED_USER_IDS` | no | Extra numeric IDs, comma-separated |
| `DATABASE_PATH` | no | SQLite file path (created on first start) |
| `TIMEZONE` | no | IANA timezone used for display and reminders |
| `REMINDER_TIME` | no | Default daily reminder time (`HH:MM`). Users can change this in Settings |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR` |

`ALLOWED_USER_IDS` may be empty. The owner is always authorized.

### 5. Start the bot

```bash
python -m app.main
```

Open Telegram, send `/start` to the bot in a **private chat**. Unauthorized users get a generic rejection and never see account data.

## Docker (local or VPS)

There is no web frontend. The interface is Telegram. The process uses **long polling**, so the host only needs outbound HTTPS to `api.telegram.org`. No inbound ports are required.

```bash
cp .env.example .env
# edit .env with BOT_TOKEN and your real OWNER_TELEGRAM_ID
# keep DEV_ALLOW_ANY_USER=false
docker compose up -d --build
docker compose logs -f
```

The database lives in the `bot-data` named volume, so it survives container recreation. The compose file uses `restart: unless-stopped`.

To stop:

```bash
docker compose down
```

`docker compose down` does **not** delete the named volume. Use `docker compose down -v` only if you intend to destroy the database.

## VPS deployment requirements

Recommended host:

- Ubuntu 22.04 or 24.04 (or equivalent)
- Docker Engine + Docker Compose plugin
- 1 vCPU, 512 MB–1 GB RAM, 5+ GB disk
- Outbound TCP 443 to Telegram (`api.telegram.org`)
- No public HTTP/HTTPS port needed for polling

On the VPS:

```bash
sudo apt-get update
sudo apt-get install -y git docker.io docker-compose-v2
sudo usermod -aG docker "$USER"
# log out and back in if this is the first Docker install

git clone git@github.com:<your-org>/banking-demo.git
cd banking-demo
cp .env.example .env
nano .env
docker compose up -d --build
```

Required `.env` values on the VPS:

- `BOT_TOKEN` — production BotFather token (not committed)
- `OWNER_TELEGRAM_ID` — your real numeric Telegram user ID
- `DEV_ALLOW_ANY_USER=false`
- `DATABASE_PATH=/app/data/bank_manager.db` is set by Compose and can stay unset in `.env`

Optional demo data (does not run on startup):

```bash
docker compose exec bot python scripts/seed_demo_accounts.py
```

The seed script is idempotent, backs up the SQLite file first, and only writes the three known VM demo accounts. Do not run it against a database that already holds real financial records.

Local `data/` and `.env` stay on the machine that created them and are not in Git. To move an existing demo database, use **Settings → Backup database** or `/backup`, copy the backup file privately, and restore it on the VPS volume. Do not commit the `.db` file.

Firewall: allow SSH to your admin IP; deny unused inbound ports. Keep the Docker volume and any backup files private.

## Backing up the database

Prefer SQLite's **online backup API** while the bot is running. Do not copy the live `.db` file with `cp` if the bot is writing — you can get a torn snapshot.

### From Telegram

Authorized users can open **Settings → Backup database** (or send `/backup`). The bot writes a timestamped file under `data/backups/` and sends it as a document. Keep that file private.

### From the host (bot running)

```bash
python - <<'PY'
import asyncio
from pathlib import Path
from app.config import load_settings
from app.database.connection import Database
from app.services.backup import backup_database

async def main():
    settings = load_settings()
    db = Database(settings.database_path)
    await db.connect()
    path = await backup_database(db, Path(settings.database_path).parent / "backups")
    await db.close()
    print(path)

asyncio.run(main())
PY
```

### From Docker

```bash
docker compose exec bot python - <<'PY'
import asyncio
from pathlib import Path
from app.database.connection import Database
from app.services.backup import backup_database
from app.config import load_settings

async def main():
    settings = load_settings()
    db = Database(settings.database_path)
    await db.connect()
    print(await backup_database(db, Path("/app/data/backups")))
    await db.close()

asyncio.run(main())
PY
```

The database file is never exposed over HTTP. Do not publish the volume or the `.db` file.

Schema changes are versioned in `app/database/schema.py` (`MIGRATIONS`). Add a new version; never edit an already-applied migration.

## Tests

Tests use isolated temporary databases and **do not** need a real Telegram token.

```bash
source .venv/bin/activate
pytest
```

## Security limitations

- Only people listed in `OWNER_TELEGRAM_ID` / `ALLOWED_USER_IDS` can use the bot.
- Sensitive actions require a private Telegram chat.
- **Do not** send bank passwords, OTP codes, session tokens, recovery phrases, or 2FA backup codes to the bot. The data model stores a password-manager reference only. A future encrypted vault table can attach to `accounts.id` without rewriting account management.
- Deposit details (IBAN, account numbers, SWIFT, …) are stored as text so leading zeros survive. They are shown only to authorized users in private chats and are **excluded from CSV exports**.
- Logs are structured and redacted; they must not contain banking identifiers or credentials.
- Telegram itself is the transport. Treat chat history as sensitive.
- SQLite is a single-file database. Protect the host disk and Docker volume.

## What this bot does not do

- It does not hold real money.
- It does not initiate transfers or withdrawals.
- It does not log into banks or read statements automatically.
- Balances are correct only if someone updates them.

## Demo accounts

The bot does **not** seed data on startup. Local SQLite files under `data/` are gitignored. To create or refresh the three VM demo accounts (Airwallex / USD) with balances, history, and withdrawals, run:

```bash
PYTHONPATH=. python scripts/seed_demo_accounts.py
```

The script is idempotent: it backs up the configured `DATABASE_PATH` first, removes only known obsolete demo fingerprints, creates missing VM accounts, and leaves any other accounts untouched.

## Project layout

```
app/
  main.py              # polling entrypoint
  config.py            # environment settings
  database/            # connection, schema, repositories
  handlers/            # Telegram commands and callbacks
  keyboards/           # inline keyboards + callback factories
  states/              # FSM forms
  services/            # business logic (no Telegram SQL)
  middleware/          # auth + errors
  utils/
tests/
```
