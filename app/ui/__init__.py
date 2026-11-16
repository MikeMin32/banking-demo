"""Operation Greenline Widget UI design system."""

from app.ui.render import banner_exists, banner_path, present_widget, render_app_screen, widget_size_ok
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
    "banner_exists",
    "banner_path",
    "dashboard_html",
    "login_html",
    "present_widget",
    "prompt_html",
    "render_app_screen",
    "settings_html",
    "transactions_html",
    "widget_size_ok",
]
