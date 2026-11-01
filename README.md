# Virtual Bank Account Manager

A private Telegram bot for tracking virtual bank accounts, recorded bank balances, and expected charges.

This is an **account tracking system**, not a bank. You type balances in by hand. The bot never logs into a bank, never scrapes a website, never talks to a banking API, and never sends a real transfer or withdrawal.

**Available balance** is what you see throughout the bot:

`available = recorded bank balance − pending expected charges`

Completing a charge deducts that amount from the recorded bank balance **once**. Cancelling a pending charge only releases the reservation. Legacy completed charges from before this accounting change are kept as history and are not deducted again.

Currencies are **never** added together. USD and EUR stay in separate totals.

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
- Four-button dashboard: Bank Accounts, Balance Summary, Add Account, Settings
- Account list buttons show line, provider, storage location, and available balance
- Compact account details with recorded bank balance, pending charges, and available balance
- Two-step copy-and-paste account creation (bank block, then login block, then review)
- Encrypted login details (mobile, email, password, 2FA). Only the owner can reveal passwords
- Expected charges: amount only; pending / completed / cancelled
- Daily stale-balance reminders (Settings only toggles them on or off)
- Page banners for major screens (`assets/banners/*.png`)
- Online SQLite backup via owner-only `/backup`

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
DEV_ALLOW_ANY_USER=false
ACCOUNT_CREDENTIALS_KEY=
```

| Variable | Required | Meaning |
|---|---|---|
| `BOT_TOKEN` | yes | Token from BotFather |
| `OWNER_TELEGRAM_ID` | yes | Your numeric Telegram user ID |
| `ALLOWED_USER_IDS` | no | Extra numeric IDs, comma-separated |
| `DATABASE_PATH` | no | SQLite file path (created on first start) |
| `TIMEZONE` | no | IANA timezone used for display and reminders |
| `REMINDER_TIME` | no | Default daily reminder time (`HH:MM`) used by the scheduler |
| `LOG_LEVEL` | no | `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `DEV_ALLOW_ANY_USER` | no | Local testing only. Does **not** grant password or backup access |
| `ACCOUNT_CREDENTIALS_KEY` | yes, to store passwords | Fernet key. Generate with `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"` |

`ALLOWED_USER_IDS` may be empty. The owner is always authorized.

If `ACCOUNT_CREDENTIALS_KEY` is missing, accounts can still be created without a password. Saving a password fails until the key is set. Losing the key makes stored passwords unrecoverable; balances and other fields remain readable.

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
- `ACCOUNT_CREDENTIALS_KEY` — Fernet key generated on the host, never committed
- `DATABASE_PATH=/app/data/bank_manager.db` is set by Compose and can stay unset in `.env`

Do **not** run `scripts/seed_demo_accounts.py` after restoring a transferred database. The bot does not seed on startup. `db.init()` only applies `CREATE TABLE IF NOT EXISTS` / versioned migrations and will not wipe rows.

Local `data/` and `.env` stay on the machine that created them and are not in Git.

## Migrate the existing SQLite database to a VPS

The live file is `data/bank_manager.db` (WAL mode). Do not `scp` that file while the bot is running. Create a consistent snapshot with the SQLite backup API, then copy that snapshot privately.

### 1. Create a snapshot on this machine

```bash
PYTHONPATH=. python scripts/export_vps_snapshot.py
```

Default output (gitignored):

`data/transfers/bank_manager-vps-snapshot.db`

Verify it locally with `PRAGMA integrity_check` (the script does this). Never commit or push this file.

### 2. Upload over SSH

```bash
chmod 600 data/transfers/bank_manager-vps-snapshot.db
scp -p data/transfers/bank_manager-vps-snapshot.db USER@VPS_HOST:~/bank_manager-vps-snapshot.db
ssh USER@VPS_HOST 'chmod 600 ~/bank_manager-vps-snapshot.db'
```

Use a key-based SSH login. Do not put the snapshot in GitHub, email, or a public object store.

### 3. Restore into the Docker volume

Inside the container the database path is **`/app/data/bank_manager.db`**.

Compose mounts the named volume **`bot-data`** at `/app/data`. Docker’s full volume name is `{project}_bot-data` (for a clone directory named `banking-demo` that is `banking-demo_bot-data`).

Restore **before** the first long-running start, or stop the bot first so WAL files are not in use:

```bash
cd banking-demo
cp .env.example .env
# set BOT_TOKEN, OWNER_TELEGRAM_ID, DEV_ALLOW_ANY_USER=false

docker compose build
docker compose create
docker compose stop bot

docker compose run --rm --no-deps --entrypoint sh \
  -v "$HOME/bank_manager-vps-snapshot.db:/snapshot.db:ro" \
  bot \
  -c 'rm -f /app/data/bank_manager.db /app/data/bank_manager.db-wal /app/data/bank_manager.db-shm && cp /snapshot.db /app/data/bank_manager.db'

docker compose up -d
```

`docker compose run` uses the same `bot-data` volume as the service, so the file lands at `/app/data/bank_manager.db`.

Then confirm inside the container:

```bash
docker compose exec bot python - <<'PY'
import sqlite3
con = sqlite3.connect("/app/data/bank_manager.db")
print(con.execute("PRAGMA integrity_check").fetchone()[0])
print(con.execute("SELECT COUNT(*) FROM accounts").fetchone()[0], "accounts")
print(con.execute("SELECT COUNT(*) FROM expected_withdrawals").fetchone()[0], "withdrawals")
print(con.execute("SELECT COUNT(*) FROM balance_history").fetchone()[0], "history")
PY
```

Do not run the demo seed after this restore. The transferred file already contains the full demo state.

Firewall: allow SSH to your admin IP; deny unused inbound ports. Keep the Docker volume and any backup files private.

## Backing up the database

Prefer SQLite's **online backup API** while the bot is running. Do not copy the live `.db` file with `cp` if the bot is writing — you can get a torn snapshot.

### From Telegram

Only the owner can send `/backup`. Ordinary authorized users cannot download the database. The bot writes a timestamped file under `data/backups/` and sends it as a document. Keep that file private. Settings no longer exposes backup, export, or help buttons.

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
- Login passwords are encrypted at rest with Fernet (`ACCOUNT_CREDENTIALS_KEY`). The key stays outside the database and Git. Only the owner can reveal a password. `DEV_ALLOW_ANY_USER` does not grant credential access.
- CSV exports never include passwords, emails, mobile numbers, or banking identifiers.
- Incoming password-containing Telegram messages are deleted when Telegram allows it. Revealed passwords still live in chat history — treat that as a security consideration.
- Logs are structured and redacted; they must not contain banking identifiers or credentials.
- Telegram itself is the transport. Treat chat history as sensitive.
- SQLite is a single-file database. Protect the host disk and Docker volume.

## Page banners

Major screens send a photo banner plus caption. Placeholder PNGs live in `assets/banners/`:

```
dashboard.png
accounts.png
account-details.png
balance-summary.png
add-account.png
expected-charges.png
login-details.png
settings.png
```

Recommended replacement size: **1280×360 PNG**. Keep the filenames. Restart the bot after replacing files so newly uploaded images are used; cached Telegram `file_id` values are process-local. If a file is missing, the bot falls back to a text message.

## What this bot does not do

- It does not hold real money.
- It does not initiate transfers or withdrawals.
- It does not log into banks or read statements automatically.
- Balances are correct only if someone updates them.

## Demo accounts

The bot does **not** seed data on startup. Local SQLite files under `data/` are gitignored. Use this script only on an empty development database. After restoring `bank_manager-vps-snapshot.db` on a VPS, skip it. To create or refresh the three VM demo accounts on a blank DB, run:

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
