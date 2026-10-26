"""Compact CallbackData factories (Telegram's 64-byte callback_data limit)."""

from __future__ import annotations

from aiogram.filters.callback_data import CallbackData


class MenuCB(CallbackData, prefix="m"):
    a: str


class AccCB(CallbackData, prefix="a"):
    o: str
    i: int = 0
    p: int = 0


class AccFieldCB(CallbackData, prefix="af"):
    i: int
    f: str


class WdCB(CallbackData, prefix="w"):
    o: str
    i: int = 0
    a: int = 0
    p: int = 0
    s: str = "pending"


class FormCB(CallbackData, prefix="f"):
    o: str


class SetCB(CallbackData, prefix="s"):
    o: str
    v: str = "-"


class DepCB(CallbackData, prefix="d"):
    o: str
    i: int = 0
    f: str = "-"


class PickCB(CallbackData, prefix="p"):
    k: str
    v: str
