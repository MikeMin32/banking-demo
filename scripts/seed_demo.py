"""Deprecated alias. Use scripts/seed_demo_accounts.py."""

from __future__ import annotations

import asyncio

from scripts.seed_demo_accounts import main

if __name__ == "__main__":
    asyncio.run(main())
