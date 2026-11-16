"""Per-chat active screen session (banner + content message IDs).

Persists across process restarts so navigation can delete the previous
banner even when the callback only references the content message.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import asdict, dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_STATE_PATH = Path("data/ui_screen_state.json")


@dataclass(slots=True)
class ActiveScreen:
    chat_id: int
    banner_message_id: int | None
    content_message_id: int
    screen: str | None = None


class ScreenSessionStore:
    """Thread-safe, per-chat screen pair tracker with JSON persistence."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DEFAULT_STATE_PATH
        self._sessions: dict[int, ActiveScreen] = {}
        self._locks: dict[int, asyncio.Lock] = {}
        self._global = asyncio.Lock()
        self._loaded = False

    def _ensure_parent(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)

    async def _load(self) -> None:
        if self._loaded:
            return
        async with self._global:
            if self._loaded:
                return
            if self.path.is_file():
                try:
                    raw = json.loads(self.path.read_text(encoding="utf-8"))
                    for key, value in (raw or {}).items():
                        chat_id = int(key)
                        self._sessions[chat_id] = ActiveScreen(
                            chat_id=chat_id,
                            banner_message_id=value.get("banner_message_id"),
                            content_message_id=int(value["content_message_id"]),
                            screen=value.get("screen"),
                        )
                except Exception:
                    logger.warning("ui screen state load failed path=%s", self.path, exc_info=True)
            self._loaded = True

    async def _save(self) -> None:
        self._ensure_parent()
        payload = {
            str(chat_id): {
                "banner_message_id": session.banner_message_id,
                "content_message_id": session.content_message_id,
                "screen": session.screen,
            }
            for chat_id, session in self._sessions.items()
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=None, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    async def lock_for(self, chat_id: int) -> asyncio.Lock:
        await self._load()
        async with self._global:
            lock = self._locks.get(chat_id)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[chat_id] = lock
            return lock

    async def get(self, chat_id: int) -> ActiveScreen | None:
        await self._load()
        return self._sessions.get(chat_id)

    async def set(
        self,
        chat_id: int,
        *,
        banner_message_id: int | None,
        content_message_id: int,
        screen: str | None,
    ) -> ActiveScreen:
        await self._load()
        session = ActiveScreen(
            chat_id=chat_id,
            banner_message_id=banner_message_id,
            content_message_id=content_message_id,
            screen=screen,
        )
        self._sessions[chat_id] = session
        try:
            await self._save()
        except Exception:
            logger.warning("ui screen state save failed chat_id=%s", chat_id, exc_info=True)
        return session

    async def pop(self, chat_id: int) -> ActiveScreen | None:
        await self._load()
        session = self._sessions.pop(chat_id, None)
        if session is not None:
            try:
                await self._save()
            except Exception:
                logger.warning("ui screen state save failed after pop chat_id=%s", chat_id, exc_info=True)
        return session

    async def clear(self, chat_id: int) -> None:
        await self.pop(chat_id)


_STORE: ScreenSessionStore | None = None


def get_screen_session_store() -> ScreenSessionStore:
    global _STORE
    if _STORE is None:
        _STORE = ScreenSessionStore()
    return _STORE


def reset_screen_session_store_for_tests(path: Path | None = None) -> ScreenSessionStore:
    """Replace the process-wide store (tests only)."""
    global _STORE
    _STORE = ScreenSessionStore(path=path)
    return _STORE
