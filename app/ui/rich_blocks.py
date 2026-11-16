"""Shared Rich Message building blocks from the approved /ui_preview prototype A."""

from __future__ import annotations

from aiogram.types import (
    InputRichBlockDetails,
    InputRichBlockDivider,
    InputRichBlockParagraph,
    InputRichBlockSectionHeading,
    InputRichBlockTable,
    InputRichMessage,
    RichBlockTableCell,
    RichTextBold,
)

from app.ui.theme import BRAND


def cell(text: str, *, align: str = "left", bold: bool = False) -> RichBlockTableCell:
    content: str | RichTextBold = RichTextBold(text=text) if bold else text
    return RichBlockTableCell(align=align, valign="middle", text=content)


def kv_table(rows: list[tuple[str, str]], *, striped: bool = True, compact: bool = True) -> InputRichBlockTable:
    cells = [[cell(label), cell(value, align="right", bold=True)] for label, value in rows]
    return InputRichBlockTable(cells=cells, is_striped=striped, is_compact=compact)


def heading(text: str, size: int) -> InputRichBlockSectionHeading:
    return InputRichBlockSectionHeading(text=text, size=size)


def paragraph(text: str | RichTextBold) -> InputRichBlockParagraph:
    return InputRichBlockParagraph(text=text)


def divider() -> InputRichBlockDivider:
    return InputRichBlockDivider()


def details(summary: str, rows: list[tuple[str, str]], *, open_: bool = False) -> InputRichBlockDetails:
    return InputRichBlockDetails(
        summary=summary,
        is_open=open_,
        blocks=[kv_table(rows, compact=True)],
    )


def brand_header(title: str, subtitle: str | None = None, *, archived: bool = False) -> list:
    brand = f"{BRAND} · Archived" if archived else BRAND
    blocks: list = [
        heading(brand, 3),
        paragraph(RichTextBold(text=title)),
    ]
    if subtitle:
        blocks.append(paragraph(subtitle))
    blocks.append(divider())
    return blocks


def rich_message(blocks: list) -> InputRichMessage:
    return InputRichMessage(blocks=blocks)
