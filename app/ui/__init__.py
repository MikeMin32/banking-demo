"""Operation Greenline Widget UI design system."""

from app.ui.render import present_widget, render_app_screen
from app.ui.screens import (
    account_details_html,
    accounts_overview_html,
    balance_summary_html,
    dashboard_html,
    login_html,
    prompt_html,
    settings_html,
    transactions_html,
)

__all__ = [
    "account_details_html",
    "accounts_overview_html",
    "balance_summary_html",
    "dashboard_html",
    "login_html",
    "present_widget",
    "prompt_html",
    "render_app_screen",
    "settings_html",
    "transactions_html",
]
