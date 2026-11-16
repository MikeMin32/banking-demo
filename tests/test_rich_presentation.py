"""Rich Message is the primary presentation when Widgets are unavailable."""

from __future__ import annotations

from aiogram.types import InputRichBlockDetails, InputRichBlockSectionHeading, InputRichBlockTable

from app.ui.rich_screens import account_details_rich, dashboard_rich, settings_rich
from app.ui.render import present_widget
from app.utils.ui_preview import assert_no_secrets, sample_account_details


def test_approved_account_details_rich_structure() -> None:
    rich = account_details_rich(sample_account_details())
    types = [getattr(getattr(b, "type", None), "value", getattr(b, "type", None)) for b in rich.blocks or []]
    assert "heading" in types
    assert "table" in types
    assert "details" in types
    assert "divider" in types
    tables = [b for b in (rich.blocks or []) if isinstance(b, InputRichBlockTable)]
    assert tables and all(t.is_striped for t in tables)
    headings = [b for b in (rich.blocks or []) if isinstance(b, InputRichBlockSectionHeading)]
    assert any(h.size == 1 and "$5,000.00" in str(h.text) for h in headings)
    details = [b for b in (rich.blocks or []) if isinstance(b, InputRichBlockDetails)]
    assert details and details[0].summary == "Account Information"
    payload = rich.model_dump_json(exclude_none=True)
    assert "OPERATION GREENLINE" in payload
    assert "Automation Direct" in payload
    assert_no_secrets(payload)


def test_dashboard_and_settings_rich_builders() -> None:
    class FakeSnap:
        accounts = []
        by_currency = {}

    dash = dashboard_rich(FakeSnap())  # type: ignore[arg-type]
    assert dash.blocks
    settings = settings_rich(reminders_enabled=True, reminder_time="09:00")
    assert any(isinstance(b, InputRichBlockDetails) for b in (settings.blocks or []))


async def test_widget_failure_falls_back_to_rich_not_plain_html() -> None:
    class FakeBot:
        def __init__(self) -> None:
            self.rich_sent = False

        async def send_widget(self, **kwargs):
            from aiogram.exceptions import TelegramBadRequest
            from aiogram.methods import SendWidget

            raise TelegramBadRequest(
                method=SendWidget(chat_id=1, html="x"),
                message="Bad Request: INPUT_MEDIA_WIDGET_NOT_ALLOWED",
            )

        async def send_rich_message(self, **kwargs):
            self.rich_sent = True
            return type("M", (), {"message_id": 42, "photo": None})()

        async def send_photo(self, **kwargs):
            return type("M", (), {"message_id": 41, "photo": [type("P", (), {"file_id": "x"})()]} )()

        async def delete_message(self, *a, **k):
            return None

    class FakeMessage:
        def __init__(self) -> None:
            self.bot = FakeBot()
            self.chat = type("C", (), {"id": 5483365623})()
            self.last = None

        async def edit_text(self, text, reply_markup=None):
            self.last = text
            return self

        async def answer(self, text, reply_markup=None):
            self.last = text
            return self

        async def delete(self):
            return None

    msg = FakeMessage()
    rich = account_details_rich(sample_account_details())
    result = await present_widget(
        msg,  # type: ignore[arg-type]
        "<html>x</html>",
        None,
        text_fallback="<b>primitive</b>",
        rich_fallback=rich,
        screen=None,
    )
    assert msg.bot.rich_sent is True
    assert result is not None
    assert msg.last is None or "primitive" not in (msg.last or "")
