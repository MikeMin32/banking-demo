"""Shared Operation Greenline Widget stylesheet (inline, no external assets)."""

from __future__ import annotations

BRAND = "OPERATION GREENLINE"

# Compact CSS using Telegram theme variables. Keep small for zlib ≤4KB budgets.
BASE_CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0;font:13px/1.35 system-ui,-apple-system,sans-serif;
color:var(--tg-theme-text-color,#e8e8ea);
background:var(--tg-theme-bg-color,#1c1c1e)}
.w{padding:11px 12px max(12px,var(--tg-content-safe-area-inset-bottom,0));
max-width:430px;min-width:280px}
.brand{font-size:10px;letter-spacing:.09em;font-weight:700;text-transform:uppercase;
color:var(--tg-theme-accent-text-color,#3dd68c)}
.title{margin:3px 0 0;font-size:16px;font-weight:700;word-break:break-word}
.sub{margin:2px 0 0;font-size:12px;color:var(--tg-theme-hint-color,#8e8e93)}
.meta{margin-top:4px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}
.accent{width:26px;height:2px;margin:7px 0 0;border-radius:2px;
background:var(--tg-theme-accent-text-color,#3dd68c)}
.card{margin-top:9px;padding:9px 11px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}
.lbl{font-size:10px;letter-spacing:.04em;text-transform:uppercase;font-weight:650;
color:var(--tg-theme-hint-color,#8e8e93)}
.bal{margin-top:2px;font-size:26px;font-weight:750;letter-spacing:-.02em;word-break:break-word}
.h{margin:0 0 4px;font-size:10px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
color:var(--tg-theme-subtitle-text-color,#aeaeb2)}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline;
padding:6px 9px;border-radius:6px}
.row:nth-child(odd){background:color-mix(in srgb,var(--tg-theme-section-separator-color,#3a3a3c) 28%,transparent)}
.k{color:var(--tg-theme-hint-color,#8e8e93);font-size:12px;flex:0 1 auto}
.v{font-weight:650;font-size:12px;text-align:right;word-break:break-word}
.muted{color:var(--tg-theme-hint-color,#8e8e93);font-weight:500}
.pos{color:var(--tg-theme-accent-text-color,#3dd68c)}
.neg{color:var(--tg-theme-destructive-text-color,#ff453a)}
.wait{color:var(--tg-theme-subtitle-text-color,#ffd60a)}
.struck{text-decoration:line-through;opacity:.72}
.date{margin:10px 0 4px;font-size:11px;font-weight:700;
color:var(--tg-theme-subtitle-text-color,#aeaeb2)}
.tx{display:flex;gap:8px;justify-content:space-between;padding:4px 0;font-size:12px}
.tx .t{color:var(--tg-theme-hint-color,#8e8e93);min-width:38px}
.tx .b{flex:1;text-align:right;font-weight:600;word-break:break-word}
.empty{padding:14px 8px;text-align:center;color:var(--tg-theme-hint-color,#8e8e93);font-size:12px}
.notice{margin-top:9px;padding:9px 11px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e);font-size:12px;white-space:pre-wrap;word-break:break-word}
.notice b,.notice strong{font-weight:700}
.notice code{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px}
.acc{margin-top:8px;padding:9px 11px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}
.acc .name{font-weight:700;font-size:13px;word-break:break-word}
.acc .prov{margin-top:1px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}
.pill{display:inline-block;margin-top:4px;padding:2px 7px;border-radius:999px;font-size:10px;
background:color-mix(in srgb,var(--tg-theme-accent-text-color,#3dd68c) 18%,transparent);
color:var(--tg-theme-accent-text-color,#3dd68c);font-weight:700}
.foot{margin-top:8px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93);text-align:right}
""".replace("\n", "")
