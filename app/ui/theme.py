"""Approved Operation Greenline Widget stylesheet + tab/accordion helpers.

Visual foundation matches the original /ui_preview HTML Widget prototype.
Kept compact for Telegram's 4 KB zlib-compressed HTML budget.
"""

from __future__ import annotations

BRAND = "OPERATION GREENLINE"

# Based on the approved ui_preview CSS (pre-widget-redesign), plus tabs/details.
BASE_CSS = """
*{box-sizing:border-box}
html,body{margin:0;padding:0;font:14px/1.35 system-ui,sans-serif;
color:var(--tg-theme-text-color,#e7e7e7);
background:var(--tg-theme-bg-color,#1c1c1e)}
.w{padding:12px 12px max(12px,var(--tg-content-safe-area-inset-bottom,0));
max-width:430px;min-width:280px}
.brand{font-size:11px;letter-spacing:.08em;font-weight:700;text-transform:uppercase;
color:var(--tg-theme-accent-text-color,#3dd68c)}
.title{margin:4px 0 0;font-size:17px;font-weight:700;word-break:break-word}
.sub{margin:2px 0 0;font-size:12px;color:var(--tg-theme-hint-color,#8e8e93)}
.meta{margin-top:4px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}
.accent{width:28px;height:2px;margin:8px 0 0;border-radius:2px;
background:var(--tg-theme-accent-text-color,#3dd68c)}
.card{margin-top:10px;padding:10px 12px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}
.lbl{font-size:11px;color:var(--tg-theme-hint-color,#8e8e93);text-transform:uppercase;
letter-spacing:.04em}
.bal{margin-top:2px;font-size:28px;font-weight:750;letter-spacing:-.02em;word-break:break-word}
.h{margin:0 0 4px;font-size:11px;font-weight:700;letter-spacing:.05em;text-transform:uppercase;
color:var(--tg-theme-subtitle-text-color,#aeaeb2)}
.rows{margin-top:2px}
.row{display:flex;justify-content:space-between;gap:10px;align-items:baseline;
padding:7px 10px;border-radius:6px}
.rows .row:nth-child(odd){background:color-mix(in srgb,var(--tg-theme-section-separator-color,#3a3a3c) 28%,transparent)}
.k{color:var(--tg-theme-hint-color,#8e8e93);font-size:12px;flex:0 1 auto}
.v{font-weight:650;font-size:13px;text-align:right;word-break:break-word}
.tabs{display:flex;gap:4px;margin-top:10px}
.tabs button{flex:1;padding:7px 4px;font:650 12px/1.2 system-ui,sans-serif;border:0;border-radius:8px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e);color:var(--tg-theme-hint-color,#8e8e93)}
.tabs button.on{background:color-mix(in srgb,var(--tg-theme-accent-text-color,#3dd68c) 22%,transparent);
color:var(--tg-theme-accent-text-color,#3dd68c)}
.panel{margin-top:8px}
.panel[hidden]{display:none!important}
details.accbox{margin-top:8px;padding:10px 12px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}
details.accbox>summary{cursor:pointer;font-weight:700;font-size:11px;letter-spacing:.05em;
text-transform:uppercase;color:var(--tg-theme-subtitle-text-color,#aeaeb2);list-style:none}
details.accbox>summary::-webkit-details-marker{display:none}
details.accbox[open]>summary{margin-bottom:6px}
.pos{color:var(--tg-theme-accent-text-color,#3dd68c)}
.neg{color:var(--tg-theme-destructive-text-color,#ff453a)}
.wait{color:#ffd60a}
.struck{text-decoration:line-through;opacity:.72}
.date{margin:10px 0 4px;font-size:11px;font-weight:700;color:var(--tg-theme-subtitle-text-color,#aeaeb2)}
.tx{display:flex;gap:8px;justify-content:space-between;padding:4px 0;font-size:12px}
.tx .t{color:var(--tg-theme-hint-color,#8e8e93);min-width:38px}
.tx .b{flex:1;text-align:right;font-weight:600;word-break:break-word}
.empty{padding:14px 8px;text-align:center;color:var(--tg-theme-hint-color,#8e8e93);font-size:12px}
.notice{margin-top:9px;padding:9px 11px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e);font-size:12px;white-space:pre-wrap;word-break:break-word}
.notice b,.notice strong{font-weight:700}
.notice code{font-family:ui-monospace,Menlo,monospace;font-size:11px}
.acc{margin-top:8px;padding:9px 11px;border-radius:10px;
background:var(--tg-theme-secondary-bg-color,#2c2c2e)}
.acc .name{font-weight:700;font-size:13px;word-break:break-word}
.acc .prov{margin-top:1px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93)}
.pill{display:inline-block;margin-top:4px;padding:2px 7px;border-radius:999px;font-size:10px;
background:color-mix(in srgb,var(--tg-theme-accent-text-color,#3dd68c) 18%,transparent);
color:var(--tg-theme-accent-text-color,#3dd68c);font-weight:700}
.foot{margin-top:8px;font-size:11px;color:var(--tg-theme-hint-color,#8e8e93);text-align:right}
""".replace("\n", "")

# Tiny tab switcher — presentation only, no bot requests.
TABS_JS = (
    "<script>(function(){var t=document.querySelectorAll('[data-tab]'),"
    "p=document.querySelectorAll('[data-panel]');function s(id){"
    "for(var i=0;i<p.length;i++)p[i].hidden=p[i].getAttribute('data-panel')!==id;"
    "for(var j=0;j<t.length;j++){var o=t[j].getAttribute('data-tab')===id;"
    "t[j].classList.toggle('on',o);}"
    "if(window.TelegramWidget&&TelegramWidget.setResizeAnchor)"
    "try{TelegramWidget.setResizeAnchor('top')}catch(e){}}"
    "for(var k=0;k<t.length;k++)(function(b){"
    "b.addEventListener('click',function(){s(b.getAttribute('data-tab'))})})(t[k]);"
    "})();</script>"
)
