"""Reusable Widget HTML fragments for Operation Greenline."""

from __future__ import annotations

from html import escape

from app.ui.theme import BASE_CSS, BRAND


def e(value: object | None, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return escape(text)


def document(body: str) -> str:
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<style>{BASE_CSS}</style></head><body><div class=\"w\">{body}</div></body></html>"
    )


def app_header(
    *,
    title: str,
    subtitle: str | None = None,
    brand: str = BRAND,
    meta: str | None = None,
) -> str:
    parts = [
        f'<div class="brand">{e(brand)}</div>',
        f'<div class="title">{e(title)}</div>',
    ]
    if subtitle:
        parts.append(f'<div class="sub">{e(subtitle)}</div>')
    if meta:
        parts.append(f'<div class="meta">{e(meta)}</div>')
    parts.append('<div class="accent"></div>')
    return "".join(parts)


def balance_card(label: str, amount: str) -> str:
    return (
        f'<div class="card"><div class="lbl">{e(label)}</div>'
        f'<div class="bal">{e(amount)}</div></div>'
    )


def section(title: str, rows_html: str) -> str:
    return f'<div class="card"><div class="h">{e(title)}</div>{rows_html}</div>'


def kv_rows(pairs: list[tuple[str, str]], *, value_class: str = "v") -> str:
    chunks: list[str] = []
    for key, value in pairs:
        chunks.append(
            f'<div class="row"><span class="k">{e(key)}</span>'
            f'<span class="{value_class}">{e(value)}</span></div>'
        )
    return "".join(chunks)


def status_pill(text: str) -> str:
    return f'<span class="pill">{e(text)}</span>'


def empty_state(message: str) -> str:
    return f'<div class="empty">{e(message)}</div>'


def notice_card(html_body: str) -> str:
    """Pass-through for trusted Telegram-HTML captions already escaped at source."""
    return f'<div class="notice">{html_body}</div>'


def account_card_block(
    *,
    name: str,
    provider: str,
    expected: str,
    current: str,
    projected: str,
    archived: bool = False,
) -> str:
    arch = status_pill("Archived") if archived else ""
    rows = kv_rows(
        [
            ("Expected", expected),
            ("Current", current),
            ("Projected", projected),
        ]
    )
    return (
        f'<div class="acc"><div class="name">{e(name)}</div>'
        f'<div class="prov">{e(provider)}</div>{arch}{rows}</div>'
    )


def date_header(label: str) -> str:
    return f'<div class="date">{e(label)}</div>'


def tx_row(*, time: str, body_html: str) -> str:
    return f'<div class="tx"><span class="t">{e(time)}</span><span class="b">{body_html}</span></div>'


def footer(text: str) -> str:
    return f'<div class="foot">{e(text)}</div>'
