"""Reusable in-Widget UI building blocks (approved preview language)."""

from __future__ import annotations

from html import escape

from app.ui.theme import BASE_CSS, BRAND, TABS_JS


def e(value: object | None, fallback: str = "—") -> str:
    if value is None:
        return fallback
    text = str(value).strip()
    if not text:
        return fallback
    return escape(text)


def document(body: str, *, with_tabs: bool = False) -> str:
    script = TABS_JS if with_tabs else ""
    return (
        "<!DOCTYPE html><html><head><meta charset=\"utf-8\">"
        "<meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">"
        f"<style>{BASE_CSS}</style></head><body><div class=\"w\">{body}</div>"
        f"{script}</body></html>"
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


def kv_rows(pairs: list[tuple[str, str]]) -> str:
    chunks = [
        f'<div class="row"><span class="k">{e(key)}</span>'
        f'<span class="v">{e(value)}</span></div>'
        for key, value in pairs
    ]
    return f'<div class="rows">{"".join(chunks)}</div>'


def section_card(title: str, rows_html: str) -> str:
    return f'<div class="card"><div class="h">{e(title)}</div>{rows_html}</div>'


def tab_bar(tabs: list[tuple[str, str]], *, active: str) -> str:
    """tabs: list of (id, label). Presentation-only; switched by TABS_JS."""
    buttons: list[str] = []
    for tab_id, label in tabs:
        cls = ' class="on"' if tab_id == active else ""
        buttons.append(
            f'<button type="button"{cls} data-tab="{e(tab_id)}">{e(label)}</button>'
        )
    return f'<div class="tabs" role="tablist">{"".join(buttons)}</div>'


def tab_panel(tab_id: str, inner_html: str, *, active: str) -> str:
    hidden = "" if tab_id == active else " hidden"
    return f'<div class="panel" data-panel="{e(tab_id)}"{hidden}>{inner_html}</div>'


def accordion(summary: str, inner_html: str, *, open_: bool = False) -> str:
    op = " open" if open_ else ""
    return (
        f'<details class="accbox"{op}><summary>{e(summary)}</summary>'
        f"{inner_html}</details>"
    )


def status_pill(text: str) -> str:
    return f'<span class="pill">{e(text)}</span>'


def empty_state(message: str) -> str:
    return f'<div class="empty">{e(message)}</div>'


def notice_card(html_body: str) -> str:
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
