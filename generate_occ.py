#!/usr/bin/env python3
"""
IndiGo (6E) Operations Control Centre  -  Orbital Topology GUI generator
========================================================================
Run:  python3 generate_occ.py
Out:  index.html + docs/index.html   (local + GitHub Pages from /docs on main)

Layout:
  ONE big rectangle ("CORE SYSTEMS FABRIC") holds everything backend:
    LEFT  : MF (own box)  ->  MS (microservices)  ->  MongoDB + AIMS DB
            (stacked-cylinder database icons below MS)
    RIGHT : SP -> EXTERNAL API -> INTERNAL API -> … -> SHARED PATH
  Only applications float, orbiting the rectangle like planets.
  API groups render as collapsed boxes (label + count on map; full list in side panel).
  Down APIs blink red on their group box and sort to the top of the list.

Loads occ_data.json when present (run extract_occ.py first). All-blue dark theme.
"""

import json
import os
import re
from pathlib import Path

CX, CY = 930, 680

GROUP_LABELS = {
    "ms": ("MICROSERVICES", "OCP microservice mesh", "#4F8BFF"),
    "sp": ("SP", "stored procedures", "#6BA4FF"),
    "external": ("EXTERNAL API", "partner gateway", "#4F8BFF"),
    "internal": ("INTERNAL API", "service mesh · REST / gRPC", "#59E0FF"),
    "jobs": ("JOBS", "cron & schedulers", "#6BA4FF"),
    "kafka_consumer": ("KAFKA CONSUMER", "topic subscribers", "#4F8BFF"),
    "kafka_producer": ("KAFKA PRODUCER", "topic publishers", "#4F8BFF"),
    "redis": ("REDIS", "cache layer", "#59E0FF"),
    "shared_path": ("SHARED PATH", "MVT paths", "#6BA4FF"),
}

GROUP_ORDER = [
    "sp",
    "external",
    "internal",
    "jobs",
    "kafka_consumer",
    "kafka_producer",
    "redis",
    "shared_path",
]

MS_SHORT_NAMES = {
    "occhub-admin-ms": "ADMIN",
    "occhub-flight-ms": "FLIGHT",
    "occhub-crew-ms": "CREW",
    "occhub-dispatch-ms": "DISP",
    "occhub-weather-ms": "WX",
    "occhub-externalcomunication-ms": "EXTCOM",
    "occhub-crewresoucedashboard-ms": "CRDASH",
    "occhub-rosterautomation-ms": "ROSTER",
    "occhub-streamorchestor-ms": "STREAM",
    "occhub-ingesthub-ms": "INGEST",
    "occhub-eventConsumer-service-ms": "EVTCON",
    "occhub-mf": "MF",
}

MON_RE = re.compile(r"\bM(\d+)\b", re.I)

# Monitoring point IDs from OCCHUB_Drawio_File_V1.drawio
MS_CELL_MON = list(range(2, 13))  # M2–M12 (11 microservices)
DB_MON = {"mongo": 13, "aims": 14}
MON_PLAN: dict[str, range | list[int]] = {
    "ms": range(2, 13),
    "mongo": [13],
    "aims": [14],
    "sp": range(15, 41),           # 26 stored procedures
    "external": range(41, 52),      # 11 partner APIs
    "shared_path": range(52, 54),   # 2 MVT paths
    "jobs": range(54, 61),          # 7 cron jobs
    "kafka_producer": range(61, 101),   # 40 topics
    "kafka_consumer": range(101, 159),  # 58 topics (diagram range)
    "redis": [159],
    "internal": range(160, 497),    # 337 REST endpoints
    "apps": range(497, 519),        # 22 floating apps
}
MF_MON = 1
MS_MF_NAME = "occhub-mf"


def parse_mon(text: str) -> int | None:
    m = MON_RE.search(text or "")
    return int(m.group(1)) if m else None


def fmt_mon(n: int) -> str:
    return f"M{n}"


def mon_range_str(nums: list[int]) -> str:
    nums = sorted({n for n in nums if n is not None})
    if not nums:
        return ""
    if len(nums) == 1:
        return fmt_mon(nums[0])
    return f"{fmt_mon(nums[0])} → {fmt_mon(nums[-1])}"


def item_mon_nums(items: list[dict]) -> list[int]:
    out: list[int] = []
    for it in items:
        n = parse_mon(it.get("mon", "")) or parse_mon(it.get("address", "")) or parse_mon(it.get("source", ""))
        if n is not None:
            out.append(n)
    return out


def item_sort_key(it: dict) -> tuple[int, str]:
    n = parse_mon(it.get("mon", "")) or parse_mon(it.get("address", "")) or parse_mon(it.get("source", ""))
    return (n if n is not None else 99999, it.get("name", ""))


def assign_group_mons(items: list[dict], nums: range | list[int]) -> None:
    slot = list(nums)
    for i, item in enumerate(sorted(items, key=item_sort_key)):
        if i < len(slot):
            item["mon"] = fmt_mon(slot[i])


def assign_monitoring(cfg: dict) -> None:
    """Attach monitoring point IDs per OCCHUB draw.io numbering."""
    cfg["mf"]["mon"] = fmt_mon(MF_MON)

    ms_entries = [
        e for e in (cfg.get("ms") or [])
        if not (isinstance(e, list) and len(e) > 1 and e[1] == MS_MF_NAME)
        and e != MS_MF_NAME
    ]
    cfg["ms"] = ms_entries
    for i, entry in enumerate(ms_entries):
        mon = fmt_mon(MS_CELL_MON[i] if i < len(MS_CELL_MON) else MS_CELL_MON[-1] + i - len(MS_CELL_MON) + 1)
        if isinstance(entry, list):
            short, full = entry[0], entry[1]
            cfg["ms"][i] = [short, full, mon]
        else:
            cfg["ms"][i] = [str(entry), str(entry), mon]

    groups = cfg.get("apiGroups") or {}

    for sid, mon_n in DB_MON.items():
        mon = fmt_mon(mon_n)
        for item in groups.get(sid, []):
            item["mon"] = mon
        for spine in cfg.get("spine") or []:
            if spine.get("id") == sid:
                spine["mon"] = mon

    ms_items = [it for it in (groups.get("ms") or []) if it.get("name") != MS_MF_NAME]
    groups["ms"] = ms_items
    name_to_mon = {}
    for entry in cfg.get("ms") or []:
        if isinstance(entry, list) and len(entry) >= 3:
            name_to_mon[entry[1]] = entry[2]
    for item in ms_items:
        item["mon"] = name_to_mon.get(item.get("name", ""), item.get("mon", ""))

    for gid, nums in MON_PLAN.items():
        if gid in ("ms", "mongo", "aims"):
            continue
        assign_group_mons(groups.get(gid) or [], nums)

    for i, app in enumerate(cfg.get("apps") or []):
        mon = fmt_mon(list(MON_PLAN["apps"])[i]) if i < len(MON_PLAN["apps"]) else fmt_mon(519 + i)
        if len(app) >= 6:
            app[5] = mon
        else:
            app.append(mon)

    group_mon: dict[str, str] = {}
    for gid in ("ms", "mongo", "aims", *GROUP_ORDER):
        nums = item_mon_nums(groups.get(gid) or [])
        if gid in MON_PLAN and not nums:
            plan = list(MON_PLAN[gid])
            group_mon[gid] = mon_range_str(plan)
        else:
            group_mon[gid] = mon_range_str(nums)

    cfg["groupMon"] = group_mon
    for box in cfg.get("groupBoxes") or []:
        box["monRange"] = group_mon.get(box["id"], "")


def ms_short_label(full: str) -> str:
    if full in MS_SHORT_NAMES:
        return MS_SHORT_NAMES[full]
    core = full.removeprefix("occhub-").removesuffix("-ms").replace("-", " ")
    parts = [p for p in core.split() if p and p.lower() not in ("service",)]
    if not parts:
        return full[:8].upper()
    if len(parts) == 1:
        return parts[0][:8].upper()
    return "".join(p[0] for p in parts if p).upper()[:8]

DEFAULT_CONFIG = {
    "viewBox": "0 0 1860 1380",
    "CX": CX,
    "CY": CY,
    "container": {"x": 480, "y": 280, "w": 900, "h": 780, "label": "CORE SYSTEMS FABRIC"},
    "mf": {"x": 700, "y": 328, "w": 250, "h": 52, "label": "MF", "sub": "MAINFRAME", "mon": "M1"},
    "hub": {"x": 700, "y": 408, "w": 390, "h": 300, "label": "MS"},
    "ms": ["ODM", "OFM", "OCM", "OWM", "ODIM", "OBM", "OLRM", "ORM", "OSM", "OIM", "OESM"],
    "spine": [
        {"id": "mongo", "label": "MongoDB", "sub": "document store", "x": 620, "y": 800, "w": 104, "h": 84, "color": "#2E7BFF"},
        {"id": "aims", "label": "AIMS DB", "sub": "system of record", "x": 780, "y": 800, "w": 104, "h": 84, "color": "#59E0FF"},
    ],
    "apiGroups": {},
    "groupBoxes": [],
    "apps": [],
    "rings": [{"rx": 800, "ry": 560}, {"rx": 1000, "ry": 680}],
    "links": [],
}


def load_occ_data(base: Path) -> dict | None:
    name = os.environ.get("OCC_DATA", "occ_data.json")
    path = base / name
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def build_config(base: Path | None = None) -> dict:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    base = base or Path(__file__).resolve().parent
    data = load_occ_data(base)
    if not data:
        return cfg

    cfg["apiGroups"] = {k: v for k, v in data.get("groups", {}).items() if v}
    cfg["dataStores"] = {
        k: cfg["apiGroups"].get(k, [])
        for k in ("mongo", "aims")
        if cfg["apiGroups"].get(k)
    }
    cfg["ms"] = [
        [ms_short_label(name), name]
        for name in (data.get("microservices") or cfg["ms"])
        if name != MS_MF_NAME
    ]
    cfg["apps"] = [
        [a["code"], a["name"], a.get("ring", 0), a.get("health", "ok"), a.get("address", "")]
        for a in data.get("apps", [])
    ]

    y = 408
    gap = 72
    box_h = 68
    boxes = []
    for gid in GROUP_ORDER:
        items = cfg["apiGroups"].get(gid, [])
        if not items:
            continue
        label, sub, color = GROUP_LABELS[gid]
        boxes.append(
            {
                "id": gid,
                "label": label,
                "sub": sub,
                "x": 1160,
                "y": y,
                "w": 300,
                "h": box_h,
                "color": color,
            }
        )
        y += gap

    cfg["groupBoxes"] = boxes
    assign_monitoring(cfg)
    return cfg


CONFIG = build_config()

TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1.0"/>
<title>6E · Operations Control Centre — Orbital Topology</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500;700&display=swap" rel="stylesheet">
<style>
  :root{
    --bg-0:#03060F;--bg-1:#060B1A;--ink:#E6EEFF;--ink-dim:#8AA0D8;--ink-faint:#52689F;
    --panel-stroke:rgba(90,140,255,.20);--indigo:#2E7BFF;--indigo-2:#6BA4FF;--cyan:#59E0FF;
    --ok:#3CC8FF;--warn:#FFC24B;--crit:#FF5C7E;--down:#FF3B4E;--violet:#4F8BFF;--grid:rgba(70,120,230,.07);
    --mono:"JetBrains Mono",ui-monospace,monospace;--disp:"Space Grotesk",system-ui,sans-serif;--body:"Inter",system-ui,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{margin:0;height:100%;background:var(--bg-0);color:var(--ink);font-family:var(--body);overflow:hidden;font-size:15px}
  #stage{position:fixed;inset:0;background:radial-gradient(1300px 850px at 50% 40%,#0B1E47 0%,var(--bg-1) 46%,var(--bg-0) 100%)}
  svg{position:absolute;inset:0;width:100%;height:100%;display:block;touch-action:none;cursor:grab}
  svg.grabbing{cursor:grabbing}

  .hud{position:absolute;z-index:5;pointer-events:none}
  .hud *{pointer-events:auto}
  .hud.brand,.hud.metrics,.hud.controls,.hud.ticker{pointer-events:auto}
  .glass{background:linear-gradient(180deg,rgba(20,30,66,.8),rgba(10,15,38,.74));border:1px solid var(--panel-stroke);
    border-radius:14px;backdrop-filter:blur(14px);box-shadow:0 12px 40px rgba(0,0,0,.45),inset 0 1px 0 rgba(255,255,255,.04)}

  .brand{top:18px;left:18px;padding:14px 18px}
  .brand .row{display:flex;align-items:center;gap:12px}
  .logo{width:38px;height:38px;border-radius:10px;display:grid;place-items:center;background:linear-gradient(135deg,var(--indigo),var(--cyan));
    font-family:var(--disp);font-weight:700;font-size:17px;box-shadow:0 0 24px rgba(46,123,255,.6)}
  .brand h1{font-family:var(--disp);font-size:16px;font-weight:600;margin:0}
  .brand .sub{font-family:var(--mono);font-size:11px;color:var(--ink-dim);letter-spacing:.6px;margin-top:2px}
  .live{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;color:var(--ok);margin-top:8px}
  .live .dot{width:7px;height:7px;border-radius:50%;background:var(--ok);box-shadow:0 0 10px var(--ok);animation:blink 1.6s infinite}
  @keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}

  .metrics{top:18px;right:18px;z-index:25;padding:14px 16px;min-width:280px;transition:opacity .28s,transform .28s,visibility .28s}
  .metrics.metrics-hidden{opacity:0;visibility:hidden;pointer-events:none;transform:translateY(-8px)}
  .metrics-head{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%;cursor:pointer;user-select:none}
  .metrics-head:hover h2{color:var(--ink)}
  .metrics h2{font-family:var(--mono);font-size:11px;letter-spacing:1.4px;color:var(--ink-dim);margin:0;text-transform:uppercase;transition:color .15s}
  .metrics-chev{font-size:11px;color:var(--ink-dim);transition:transform .3s cubic-bezier(.22,1,.36,1)}
  .metrics.open .metrics-chev{transform:rotate(180deg)}
  .metrics-body{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s cubic-bezier(.22,1,.36,1),opacity .25s,margin .35s;margin-top:0}
  .metrics.open .metrics-body{max-height:420px;opacity:1;margin-top:10px;overflow-y:auto}
  .mgrid{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
  #m-probe{font-family:var(--mono);font-size:11px;color:var(--ink-dim);line-height:1.3}
  .metric{background:rgba(8,12,30,.55);border:1px solid rgba(120,150,255,.12);border-radius:10px;padding:9px 10px}
  .metric .k{font-family:var(--mono);font-size:10px;letter-spacing:.6px;color:var(--ink-dim);text-transform:uppercase}
  .metric .v{font-family:var(--disp);font-size:21px;font-weight:600;margin-top:3px;line-height:1}
  .metric .u{font-size:11px;color:var(--ink-dim);font-family:var(--mono);margin-left:3px}
  .spark{margin-top:10px;height:34px;width:100%}

  .controls{bottom:18px;left:18px;padding:12px 14px;display:flex;flex-direction:column;gap:10px}
  .legend-head{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;user-select:none}
  .legend-head:hover h2{color:var(--ink)}
  .legend-head h2{font-family:var(--mono);font-size:11px;letter-spacing:1.4px;color:var(--ink-dim);margin:0;text-transform:uppercase;transition:color .15s}
  .legend-chev{font-size:11px;color:var(--ink-dim);transition:transform .3s cubic-bezier(.22,1,.36,1)}
  .legend-panel.open .legend-chev{transform:rotate(180deg)}
  .legend-body{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s cubic-bezier(.22,1,.36,1),opacity .25s,margin .35s;margin-top:0}
  .legend-panel.open .legend-body{max-height:80px;opacity:1;margin-top:8px}
  .legend{display:flex;gap:14px;flex-wrap:wrap}
  .lg{display:flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;color:var(--ink-dim)}
  .lg i{width:10px;height:10px;border-radius:50%;display:inline-block}
  .btns{display:flex;gap:8px;flex-wrap:wrap}
  button.ctl{font-family:var(--mono);font-size:11.5px;color:var(--ink);background:rgba(30,42,82,.7);border:1px solid var(--panel-stroke);
    border-radius:9px;padding:8px 12px;cursor:pointer;transition:.15s}
  button.ctl:hover{background:rgba(46,123,255,.35);border-color:var(--indigo-2);transform:translateY(-1px)}
  button.ctl.active{background:rgba(46,123,255,.45);border-color:var(--indigo-2)}
  .search{display:flex;align-items:center;gap:8px;background:rgba(8,12,30,.6);border:1px solid var(--panel-stroke);border-radius:9px;padding:6px 10px}
  .search input{background:none;border:none;outline:none;color:var(--ink);font-family:var(--mono);font-size:12px;width:150px}
  .search input::placeholder{color:var(--ink-faint)}

  .ticker{bottom:18px;right:18px;width:380px;padding:12px 14px;display:flex;flex-direction:column}
  .ticker-head{display:flex;align-items:center;justify-content:space-between;gap:12px;cursor:pointer;user-select:none}
  .ticker-head:hover h2{color:var(--ink)}
  .ticker h2{font-family:var(--mono);font-size:11px;letter-spacing:1.4px;color:var(--ink-dim);margin:0;text-transform:uppercase;transition:color .15s;display:flex;justify-content:space-between;flex:1;gap:8px}
  .ticker-chev{font-size:11px;color:var(--ink-dim);transition:transform .3s cubic-bezier(.22,1,.36,1)}
  .ticker.open .ticker-chev{transform:rotate(180deg)}
  .ticker-body{max-height:0;overflow:hidden;opacity:0;transition:max-height .35s cubic-bezier(.22,1,.36,1),opacity .25s,margin .35s;margin-top:0;flex:1;display:flex;flex-direction:column;min-height:0}
  .ticker.open .ticker-body{max-height:120px;opacity:1;margin-top:8px}
  .feed{flex:1;overflow:hidden;font-family:var(--mono);font-size:11.5px;line-height:1.7;mask-image:linear-gradient(180deg,transparent,#000 18%,#000 100%)}
  .feed .e{display:flex;gap:8px;white-space:nowrap;opacity:0;animation:rise .5s forwards}
  @keyframes rise{from{opacity:0;transform:translateY(6px)}to{opacity:1;transform:none}}
  .feed .t{color:var(--ink-faint)}.feed .ok{color:var(--ok)}.feed .warn{color:var(--warn)}.feed .crit{color:var(--crit)}.feed .id{color:var(--cyan)}

  .panel{top:0;right:0;height:100%;width:420px;transform:translateX(108%);transition:transform .42s cubic-bezier(.22,1,.36,1);
    z-index:8;border-radius:18px 0 0 18px;display:flex;flex-direction:column;pointer-events:none}
  .panel.open{transform:none;pointer-events:auto}
  .panel .ph{padding:20px 22px 16px;border-bottom:1px solid var(--panel-stroke)}
  .panel .code{font-family:var(--disp);font-size:32px;font-weight:700;line-height:1}
  .panel .name{color:var(--ink-dim);font-size:14px;margin-top:6px}
  .pill{display:inline-flex;align-items:center;gap:6px;font-family:var(--mono);font-size:11px;padding:4px 9px;border-radius:20px;margin-top:12px;text-transform:uppercase}
  .pb{flex:1;overflow-y:auto;overflow-x:hidden;padding:18px 22px;-webkit-overflow-scrolling:touch}
  .kv{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid rgba(120,150,255,.08);font-size:13px}
  .kv .k{color:var(--ink-dim);font-family:var(--mono);font-size:11px}.kv .v{font-family:var(--mono)}
  .sect{font-family:var(--mono);font-size:11px;letter-spacing:1.2px;color:var(--ink-dim);text-transform:uppercase;margin:18px 0 8px}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{font-family:var(--mono);font-size:11px;padding:4px 9px;border-radius:7px;background:rgba(46,123,255,.18);border:1px solid rgba(110,139,255,.3);color:var(--indigo-2)}
  .pclose{position:absolute;top:16px;right:16px;width:30px;height:30px;border-radius:8px;border:1px solid var(--panel-stroke);background:rgba(8,12,30,.6);color:var(--ink);cursor:pointer;font-size:15px}
  .barwrap{height:6px;background:rgba(255,255,255,.06);border-radius:6px;overflow:hidden;margin-top:6px}.bar{height:100%;border-radius:6px}

  text{font-family:var(--mono);fill:var(--ink);user-select:none}
  .mon-tag{fill:#FFAB40 !important;font-weight:700}

  /* glow on hover (every node) */
  .nodeRect{cursor:pointer;transition:filter .18s}
  .nodeRect:hover{filter:url(#hoverglow)}
  .nodeRect:hover>rect{stroke:#dbe4ff}
  .nodeRect:hover .db-stroke{stroke:#dbe4ff}
  .db-node{cursor:pointer;transition:filter .18s}
  .db-node:hover{filter:url(#hoverglow)}
  .planet{cursor:pointer;transition:filter .18s}
  .planet:hover{filter:url(#hoverglow)}
  .dim{opacity:.12;transition:opacity .25s}.hot{opacity:1 !important}

  /* red blink for down external APIs / alarms */
  @keyframes blinkred{0%,45%{opacity:1}55%,100%{opacity:.1}}
  .blink{animation:blinkred .85s infinite}
  .extrow.searchhit>rect{stroke:var(--cyan);stroke-width:2}
  .apilist{display:flex;flex-direction:column;gap:6px}
  .apirow{display:flex;align-items:flex-start;gap:10px;padding:9px 10px;border-radius:8px;background:rgba(46,123,255,.08);border:1px solid rgba(110,139,255,.18);font-family:var(--mono);font-size:13px}
  .apirow.apiwarn{background:rgba(255,194,75,.08);border-color:rgba(255,194,75,.35)}
  .apirow.apidown{background:rgba(255,59,78,.10);border-color:rgba(255,59,78,.4)}
  .apirow.apiok{background:rgba(46,123,255,.08);border-color:rgba(110,139,255,.22)}
  .apidot{width:9px;height:9px;border-radius:50%;flex:0 0 auto;margin-top:4px;box-shadow:0 0 8px currentColor}
  .apibody{flex:1;min-width:0}
  .apiname{font-size:13px;line-height:1.35;word-break:break-word}
  .apiaddr{font-size:10px;color:var(--ink-dim);margin-top:3px;line-height:1.4;word-break:break-all}
  .apistat{font-size:10px;letter-spacing:.5px;flex:0 0 auto;margin-top:2px}
  .apibadge{display:inline-block;font-size:8.5px;padding:1px 5px;border-radius:4px;margin-right:6px;background:rgba(89,224,255,.15);color:#BFEFFF;vertical-align:middle}
  .apibadge.grp{background:rgba(79,139,255,.22);color:#B8CCFF}
  .apibadge.mon{background:rgba(255,171,64,.14);color:#FFAB40;border:1px solid rgba(255,171,64,.35)}

  .mstip{position:fixed;z-index:25;pointer-events:none;opacity:0;transition:opacity .12s;
    font-family:var(--mono);font-size:10.5px;padding:7px 11px;border-radius:9px;
    background:linear-gradient(180deg,rgba(20,30,66,.94),rgba(10,15,38,.9));
    border:1px solid var(--panel-stroke);color:var(--ink);box-shadow:0 8px 28px rgba(0,0,0,.45);
    max-width:320px;white-space:nowrap}
  .mstip.show{opacity:1}
  .mstip .short{color:var(--cyan);font-weight:600;margin-right:8px}
  .mstip .full{color:var(--ink-dim);font-size:10px}

  /* edit mode */
  body.edit-mode svg{cursor:default}
  body.edit-mode .nodeRect,body.edit-mode .planet{cursor:move}
  body.edit-mode .editable-selected{filter:url(#hoverglow)}
  body.edit-mode .editable-selected>rect,body.edit-mode .editable-selected .db-stroke{stroke:#59E0FF !important;stroke-width:2.2}
  .edit-outline{fill:none;stroke:#59E0FF;stroke-width:1.6;stroke-dasharray:6 4;pointer-events:none}
  .edit-handle{fill:#0B1530;stroke:#59E0FF;stroke-width:1.4;cursor:pointer}
  .edit-handle.n,.edit-handle.s{cursor:ns-resize}
  .edit-handle.e,.edit-handle.w{cursor:ew-resize}
  .edit-handle.ne,.edit-handle.sw{cursor:nesw-resize}
  .edit-handle.nw,.edit-handle.se{cursor:nwse-resize}
  .edit-bar{position:fixed;top:18px;left:50%;transform:translateX(-50%);z-index:30;display:none;align-items:center;gap:10px;padding:10px 16px;font-family:var(--mono);font-size:11.5px}
  body.edit-mode .edit-bar{display:flex}
  .edit-bar .hint{color:var(--ink-dim)}
  .edit-bar .dirty{color:var(--warn)}
  button.ctl.save{background:rgba(60,200,255,.22);border-color:var(--cyan)}
  button.ctl.save:hover{background:rgba(60,200,255,.38)}
  .edit-props{position:fixed;top:80px;right:18px;z-index:30;display:none;flex-direction:column;gap:8px;padding:14px 16px;min-width:200px;font-family:var(--mono);font-size:11px}
  body.edit-mode .edit-props.show{display:flex}
  .edit-props h3{margin:0 0 4px;font-size:10px;letter-spacing:1.2px;color:var(--ink-dim);text-transform:uppercase}
  .edit-props label{display:flex;align-items:center;justify-content:space-between;gap:10px;color:var(--ink-dim)}
  .edit-props input{width:72px;background:rgba(8,12,30,.7);border:1px solid var(--panel-stroke);border-radius:6px;color:var(--ink);font-family:var(--mono);font-size:11px;padding:5px 7px;text-align:right}
  .edit-toast{position:fixed;bottom:90px;left:50%;transform:translateX(-50%) translateY(12px);z-index:35;padding:10px 18px;border-radius:10px;
    background:rgba(20,30,66,.95);border:1px solid var(--cyan);color:var(--cyan);font-family:var(--mono);font-size:12px;opacity:0;pointer-events:none;transition:.25s}
  .edit-toast.show{opacity:1;transform:translateX(-50%) translateY(0)}

  @media (max-width:1100px){.ticker,.metrics{display:none}}
</style>
</head>
<body>
<div id="stage">
  <svg id="svg" preserveAspectRatio="xMidYMid meet">
    <defs>
      <radialGradient id="gHub" cx="50%" cy="35%" r="80%"><stop offset="0%" stop-color="#17326F"/><stop offset="100%" stop-color="#081038"/></radialGradient>
      <linearGradient id="gContainer" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(18,38,92,.55)"/><stop offset="100%" stop-color="rgba(6,13,36,.62)"/></linearGradient>
      <linearGradient id="gPanel" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="rgba(20,40,92,.92)"/><stop offset="100%" stop-color="rgba(8,15,42,.94)"/></linearGradient>
      <radialGradient id="gPlanet" cx="35%" cy="30%" r="75%"><stop offset="0%" stop-color="#2A4FA6"/><stop offset="100%" stop-color="#0D1842"/></radialGradient>
      <radialGradient id="gCore" cx="50%" cy="50%" r="50%"><stop offset="0%" stop-color="rgba(46,123,255,.85)"/><stop offset="55%" stop-color="rgba(46,123,255,.18)"/><stop offset="100%" stop-color="rgba(46,123,255,0)"/></radialGradient>
      <filter id="glow" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <filter id="hoverglow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="6" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge></filter>
      <filter id="softglow" x="-80%" y="-80%" width="260%" height="260%"><feGaussianBlur stdDeviation="9"/></filter>
    </defs>
    <g id="viewport">
      <g id="layer-grid"></g><g id="layer-rings"></g><g id="layer-links"></g>
      <g id="layer-particles"></g><g id="layer-core"></g><g id="layer-link-labels"></g><g id="layer-planets"></g>
      <g id="layer-edit-ui"></g>
    </g>
  </svg>

  <div class="hud glass brand">
    <div class="row"><div class="logo">6E</div>
      <div><h1>Operations Control Centre</h1><div class="sub">IGA · OCP L3 PLATFORM · JOC INTEGRATION FABRIC</div></div></div>
    <div class="live"><span class="dot"></span>LIVE · ZPL-OCP-BSTN2 · <span id="clock"></span></div>
  </div>

  <div class="hud glass metrics" id="metrics">
    <div class="metrics-head" id="metrics-toggle">
      <h2>Fabric Observability</h2>
      <span class="metrics-chev">▾</span>
    </div>
    <div class="metrics-body">
      <div class="mgrid">
        <div class="metric"><div class="k">Throughput</div><div class="v"><span id="m-tps">—</span><span class="u">msg/s</span></div></div>
        <div class="metric"><div class="k">p95 latency</div><div class="v"><span id="m-lat">—</span><span class="u">ms</span></div></div>
        <div class="metric"><div class="k">Error rate</div><div class="v"><span id="m-err">—</span><span class="u">%</span></div></div>
        <div class="metric"><div class="k">Nodes up</div><div class="v"><span id="m-up">—</span></div></div>
        <div class="metric"><div class="k">Kafka lag</div><div class="v"><span id="m-lag">—</span></div></div>
        <div class="metric"><div class="k">APIs down</div><div class="v"><span id="m-down" style="color:var(--down)">—</span></div></div>
        <div class="metric"><div class="k">APIs listed</div><div class="v"><span id="m-apis">—</span></div></div>
        <div class="metric"><div class="k">Probe</div><div class="v" style="font-size:11px"><span id="m-probe">—</span></div></div>
      </div>
      <svg class="spark" id="spark" viewBox="0 0 300 34" preserveAspectRatio="none"></svg>
    </div>
  </div>

  <div class="hud glass controls">
    <div class="legend-panel" id="legend-panel">
      <div class="legend-head" id="legend-toggle">
        <h2>Status Legend</h2>
        <span class="legend-chev">▾</span>
      </div>
      <div class="legend-body">
        <div class="legend">
          <span class="lg"><i style="background:var(--ok)"></i>Healthy</span>
          <span class="lg"><i style="background:var(--warn)"></i>Degraded</span>
          <span class="lg"><i style="background:var(--down)"></i>Down / Critical</span>
          <span class="lg"><i style="background:var(--cyan)"></i>Data flow</span>
        </div>
      </div>
    </div>
    <div class="search">🔍<input id="search" placeholder="find app / API / M#…"></div>
    <div class="btns">
      <button class="ctl" id="b-all">☰ All APIs</button>
      <button class="ctl" id="b-orbit">▶ Orbit</button>
      <button class="ctl active" id="b-flow">✦ Flow</button>
      <button class="ctl" id="b-in">+</button>
      <button class="ctl" id="b-out">−</button>
      <button class="ctl" id="b-fit">⤢ Fit</button>
      <button class="ctl" id="b-edit">✎ Edit</button>
      <button class="ctl save" id="b-save-edit" style="display:none" title="Saved automatically">💾 Saved</button>
      <button class="ctl" id="b-reset-layout" style="display:none" title="Restore original layout">↺ Reset</button>
      <button class="ctl" id="b-cancel-edit" style="display:none">✕ Cancel</button>
    </div>
  </div>

  <div class="hud glass edit-bar" id="edit-bar">
    <span class="hint">Edit mode — drag to move · changes save automatically</span>
    <span class="dirty" id="edit-dirty" style="display:none">● saving…</span>
  </div>
  <div class="hud glass edit-props" id="edit-props">
    <h3 id="edit-props-title">—</h3>
    <label>X <input type="number" id="ep-x" step="1"></label>
    <label>Y <input type="number" id="ep-y" step="1"></label>
    <label>W <input type="number" id="ep-w" step="1" min="20"></label>
    <label>H <input type="number" id="ep-h" step="1" min="16"></label>
    <label id="ep-r-wrap" style="display:none">R <input type="number" id="ep-r" step="1" min="20"></label>
  </div>
  <div class="edit-toast" id="edit-toast"></div>

  <div class="hud glass ticker" id="ticker">
    <div class="ticker-head" id="ticker-toggle">
      <h2>Event Stream <span id="eps" style="color:var(--cyan)"></span></h2>
      <span class="ticker-chev">▾</span>
    </div>
    <div class="ticker-body">
      <div class="feed" id="feed"></div>
    </div>
  </div>

  <div class="hud glass panel" id="panel">
    <button class="pclose" id="pclose">✕</button>
    <div class="ph"><div class="code" id="p-code">—</div><div class="name" id="p-name">—</div><div class="pill" id="p-status">—</div></div>
    <div class="pb" id="p-body"></div>
  </div>
  <div id="mstip" class="mstip"></div>
</div>

<script>
const CFG = __CONFIG__;
const NS='http://www.w3.org/2000/svg';
const el=(t,a={})=>{const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;};
const HC={ok:'#3CC8FF',warn:'#FFC24B',crit:'#FF5C7E',down:'#FF3B4E'};
const lerp=(a,b,t)=>a+(b-a)*t, R=(a,b)=>a+Math.random()*(b-a);
const $=id=>document.getElementById(id);
const Lgrid=$('layer-grid'),Lrings=$('layer-rings'),Llinks=$('layer-links'),
      Lpart=$('layer-particles'),Lcore=$('layer-core'),LlinkLbl=$('layer-link-labels'),Lplanets=$('layer-planets'),LeditUi=$('layer-edit-ui');
const svg=$('svg'); svg.setAttribute('viewBox',CFG.viewBox);
const VB=CFG.viewBox.split(' ').map(Number);
let orbitOn=false,flowOn=true,dragging=false,selected=null;
let editMode=false,layoutDirty=false,savedLayoutSnapshot=null,selectedEditId=null,editDrag=null;
let view={x:0,y:0,k:1};

/* background */
(function(){
  for(let x=0;x<=VB[2];x+=80) Lgrid.appendChild(el('line',{x1:x,y1:0,x2:x,y2:VB[3],stroke:'var(--grid)'}));
  for(let y=0;y<=VB[3];y+=80) Lgrid.appendChild(el('line',{x1:0,y1:y,x2:VB[2],y2:y,stroke:'var(--grid)'}));
  for(let i=0;i<170;i++) Lgrid.appendChild(el('circle',{cx:R(0,VB[2]),cy:R(0,VB[3]),r:R(.4,1.6),fill:'#9fb0ff',opacity:R(.05,.5)}));
})();

/* core glow + radar */
Lcore.appendChild(el('circle',{cx:CFG.CX,cy:CFG.CY,r:420,fill:'url(#gCore)',opacity:.5}));
for(let i=0;i<3;i++){
  const c=el('circle',{cx:CFG.CX,cy:CFG.CY,r:90,fill:'none',stroke:'rgba(46,123,255,.45)','stroke-width':1.4});
  c.append(el('animate',{attributeName:'r',values:'90;540',dur:'4.8s',begin:(i*1.6)+'s',repeatCount:'indefinite'}),
           el('animate',{attributeName:'opacity',values:'.5;0',dur:'4.8s',begin:(i*1.6)+'s',repeatCount:'indefinite'}));
  Lcore.appendChild(c);
}

CFG.rings.forEach(r=>Lrings.appendChild(el('ellipse',{cx:CFG.CX,cy:CFG.CY,rx:r.rx,ry:r.ry,fill:'none',
  stroke:'rgba(110,139,255,.14)','stroke-width':1,'stroke-dasharray':'2 8'})));

function panel(p,{x,y,w,h,fill='url(#gPanel)',stroke='var(--panel-stroke)',rx=14,sw=1.2}){
  const r=el('rect',{x:x-w/2,y,width:w,height:h,rx,fill,stroke,'stroke-width':sw});p.appendChild(r);return r;}
function label(p,x,y,txt,o={}){
  const t=el('text',{x,y,'text-anchor':o.anchor||'middle','dominant-baseline':o.base||'middle','font-size':o.size||13,
    fill:o.fill||'var(--ink)','font-weight':o.weight||400,'letter-spacing':o.ls||0,'font-family':o.font||'var(--mono)'});
  t.textContent=txt;p.appendChild(t);return t;}
const MON_COLOR='#FFAB40';
function monLabel(p,x,y,mon,o={}){if(!mon)return null;const t=label(p,x,y+(o.dy||0),mon,{size:o.size||7.5,fill:o.fill||MON_COLOR,weight:600,ls:.3,anchor:o.anchor||'middle',base:o.base||'middle'});t.setAttribute('class','mon-tag');return t;}
function monNum(s){const m=String(s||'').match(/\bM(\d+)\b/i);return m?parseInt(m[1],10):null;}
function normMonQuery(q){const t=q.trim().toUpperCase();if(!t)return null;if(/^M\d+$/.test(t))return t;const d=t.replace(/\D/g,'');return d?('M'+d):null;}
function itemMon(it){return it.mon||(it.address&&String(it.address).match(/^M\d+/i)?.[0])||'';}
function sortApiItems(items){
  const pri={down:0,crit:0,warn:1,ok:2};
  return [...items].sort((a,b)=>{
    const pa=pri[a.health]??2,pb=pri[b.health]??2;
    if(pa!==pb)return pa-pb;
    const ma=monNum(itemMon(a)),mb=monNum(itemMon(b));
    if(ma!=null&&mb!=null&&ma!==mb)return ma-mb;
    if(ma!=null&&mb==null)return-1;
    if(ma==null&&mb!=null)return 1;
    return a.name.localeCompare(b.name);
  });
}
function matchesMonQuery(q,it){
  const want=normMonQuery(q);if(!want)return false;
  const n=monNum(want),have=monNum(itemMon(it)||it.source||'');
  return n!==null&&have===n;
}
function dbCylinder(g,cx,topY,w,h,color,anyDown){
  const hexRgb=h=>[parseInt(h.slice(1,3),16),parseInt(h.slice(3,5),16),parseInt(h.slice(5,7),16)];
  const rgbHex=(r,g,b)=>'#'+[r,g,b].map(v=>Math.max(0,Math.min(255,Math.round(v))).toString(16).padStart(2,'0')).join('');
  const lighten=(hex,a)=>{const[r,g,b]=hexRgb(hex);return rgbHex(r+(255-r)*a,g+(255-g)*a,b+(255-b)*a);};
  const darken=(hex,a)=>{const[r,g,b]=hexRgb(hex);return rgbHex(r*(1-a),g*(1-a),b*(1-a));};
  const rx=w/2,ry=Math.max(11,w*.12);
  const stroke=anyDown?'#FF3B4E':darken(color,.42);
  const strokes=[];
  const side=darken(color,.14);
  const bandH=(h-ry*1.6)/3;
  g.appendChild(el('rect',{x:cx-rx,y:topY+ry,width:w,height:h-ry*1.15,fill:side,stroke:'none'}));
  for(let i=1;i<3;i++){
    const by=topY+ry+i*bandH;
    const band=el('ellipse',{cx,cy:by,rx:rx*.97,ry:ry*.58,fill:darken(color,.06+i*.07),stroke,'stroke-width':1.3,class:'db-stroke'});
    g.appendChild(band);strokes.push(band);
  }
  const top=el('ellipse',{cx,cy:topY+ry,rx,ry,fill:lighten(color,.24),stroke,'stroke-width':2,class:'db-stroke'});
  g.appendChild(top);strokes.push(top);
  g.appendChild(el('ellipse',{cx,cy:topY+ry-2,rx:rx*.68,ry:ry*.5,fill:lighten(color,.4),stroke:'none'}));
  const bot=el('ellipse',{cx,cy:topY+h-ry*.42,rx,ry:ry*.82,fill:darken(color,.28),stroke,'stroke-width':1.6,class:'db-stroke'});
  g.appendChild(bot);strokes.push(bot);
  return strokes;
}

const NODES={};

/* ===== API group registry (all groups use the same side-panel list) ===== */
const API_GROUPS=CFG.apiGroups||{};
const GROUP_UI={};
let openGroupId=null, openGroupHl=null;
const allApiCount=()=>Object.values(API_GROUPS).flat().length;
const countHealth=()=>{
  const flat=Object.values(API_GROUPS).flat();
  return{
    down:flat.filter(s=>s.health==='down'||s.health==='crit').length,
    warn:flat.filter(s=>s.health==='warn').length,
    ok:flat.filter(s=>s.health==='ok').length,
    total:flat.length
  };
};
function applyItemHealth(group,id,health,detail,latency){
  const items=API_GROUPS[group]; if(!items)return;
  const it=items.find(x=>x.name===id); if(!it)return;
  it.health=health;
  if(detail)it.probeDetail=detail;
  if(latency!=null)it.latency_ms=latency;
}
function refreshGroupBox(id){
  const ui=GROUP_UI[id]; if(!ui)return;
  const items=groupItems(id);
  const anyDown=items.some(i=>i.health==='down'||i.health==='crit');
  const anyWarn=items.some(i=>i.health==='warn');
  const dn=items.filter(i=>i.health==='down'||i.health==='crit').length;
  const wn=items.filter(i=>i.health==='warn').length;
  if(ui.dot){
    ui.dot.setAttribute('fill',anyDown?HC.down:(anyWarn?HC.warn:HC.ok));
    ui.dot.classList.toggle('blink',anyDown);
  }
  if(ui.panel){
    ui.panel.setAttribute('stroke',anyDown?'rgba(255,59,78,.65)':(anyWarn?'rgba(255,194,75,.55)':ui.baseColor));
    ui.panel.setAttribute('stroke-width',anyDown?'1.8':'1.3');
  }
  if(ui.blinkRect){
    if(anyDown)ui.blinkRect.classList.add('blink');
    else{ui.blinkRect.remove();ui.blinkRect=null;}
  }else if(anyDown&&ui.g){
    const box=(CFG.groupBoxes||[]).find(b=>b.id===id);
    if(box){
      ui.blinkRect=el('rect',{x:box.x-box.w/2,y:box.y,width:box.w,height:box.h,rx:13,fill:'none',stroke:'#FF3B4E','stroke-width':2,class:'blink'});
      ui.g.insertBefore(ui.blinkRect,ui.g.firstChild);
    }
  }
  if(ui.title)ui.title.setAttribute('fill',anyDown?'#FF8A98':(anyWarn?'#FFE2A8':'var(--ink)'));
  if(ui.hint){
    const uiBox=(CFG.groupBoxes||[]).find(b=>b.id===id);
    const monR=(uiBox&&uiBox.monRange)||(CFG.groupMon&&CFG.groupMon[id])||'';
    let hint=items.length+' APIs · tap to view';
    if(anyDown)hint=dn+' of '+items.length+' down · tap to view';
    else if(anyWarn)hint=wn+' of '+items.length+' warn · tap to view';
    if(monR)hint=monR+' · '+hint;
    ui.hint.textContent=hint;
  }
}
function refreshSpineBox(id){
  const ui=GROUP_UI[id]; if(!ui)return;
  const store=groupItems(id);
  const anyDown=store.some(i=>i.health==='down'||i.health==='crit');
  const stroke=anyDown?'rgba(255,59,78,.65)':ui.baseColor;
  if(ui.strokes) ui.strokes.forEach(e=>e.setAttribute('stroke',stroke));
  else if(ui.panel) ui.panel.setAttribute('stroke',stroke);
  ui.dot.setAttribute('fill',anyDown?HC.down:HC.ok);
}
function refreshAllGroupUI(){
  (CFG.groupBoxes||[]).forEach(b=>refreshGroupBox(b.id));
  (CFG.spine||[]).forEach(s=>refreshSpineBox(s.id));
  refreshGroupBox('ms');
}
function applyHealthPayload(data){
  if(!data||!data.groups)return;
  for(const [gid,items] of Object.entries(data.groups)){
    items.forEach(row=>applyItemHealth(gid,row.name,row.health,row.detail,row.latency_ms));
  }
  refreshAllGroupUI();
  const h=countHealth();
  $('m-down').textContent=h.down;
  $('m-up').textContent=h.ok+'/'+h.total;
  $('m-apis').textContent=h.total;
  if(openGroupId==='__all__')openAllApis(openGroupHl);
  else if(openGroupId)openGroupBox(openGroupId,openGroupHl);
}
async function pollHealth(force){
  try{
    const r=await fetch('/api/health'+(force?'?force=1':''));
    if(!r.ok)throw new Error('HTTP '+r.status);
    const data=await r.json();
    applyHealthPayload(data);
  const ts=data.updated?new Date(data.updated).toLocaleTimeString('en-GB',{hour12:false}):'live';
    $('m-probe').textContent=(data.api_base?'gateway':'diagram')+' · '+ts;
  }catch(e){
    $('m-probe').textContent='offline · diagram';
  }
}
const GROUP_META={
  ms:['MICROSERVICES','OCP microservice mesh'],
  mongo:['MongoDB','document store'],
  aims:['AIMS DB','system of record'],
};
function groupItems(id){return API_GROUPS[id]||[];}
function groupTitle(id){
  const box=(CFG.groupBoxes||[]).find(b=>b.id===id);
  if(box) return [box.label,box.sub];
  return GROUP_META[id]||[id.toUpperCase(),''];
}
const GROUP_ORDER=['ms','mongo','aims','sp','external','internal','jobs','kafka_consumer','kafka_producer','redis','shared_path'];
function allApiItems(){
  const out=[];
  GROUP_ORDER.forEach(gid=>groupItems(gid).forEach(it=>out.push({...it,_group:gid})));
  return out;
}
function renderApiList(items,hl,showGroup){
  const list=document.createElement('div');
  list.className='apilist';
  sortApiItems(items).forEach(it=>{
    const isDown=(it.health==='down'||it.health==='crit');
    const isWarn=(it.health==='warn');
    const col=isDown?'var(--down)':(isWarn?'var(--warn)':'var(--ok)');
    const lab=isDown?'DOWN':(isWarn?'WARN':'OK');
    const row=document.createElement('div');
    row.className='apirow'+(isDown?' apidown':(isWarn?' apiwarn':' apiok'));
    if(hl&&(it.name.toUpperCase().includes(hl)||(it.address&&it.address.toUpperCase().includes(hl))||matchesMonQuery(hl,it))){
      row.style.outline='1px solid var(--cyan)'; row.style.outlineOffset='2px';
    }
    const dot=document.createElement('span');
    dot.className='apidot'+(isDown?' blink':'');
    dot.style.cssText='background:'+col+';color:'+col;
    const body=document.createElement('div');
    body.className='apibody';
    if(showGroup&&it._group){const g=document.createElement('span');g.className='apibadge grp';g.textContent=it._group.toUpperCase();body.appendChild(g);}
    const mon=itemMon(it);
    if(mon){const mb=document.createElement('span');mb.className='apibadge mon';mb.textContent=mon;body.appendChild(mb);}
    if(it.method){const b=document.createElement('span');b.className='apibadge';b.textContent=it.method;body.appendChild(b);}
    const nm=document.createElement('span');nm.className='apiname';nm.textContent=it.name;body.appendChild(nm);
    if(it.address){const ad=document.createElement('div');ad.className='apiaddr';ad.textContent=it.address;body.appendChild(ad);}
    if(it.probeDetail){const pd=document.createElement('div');pd.className='apiaddr';pd.style.color=isDown?'#FF9AA8':(isWarn?'#FFE2A8':'var(--cyan)');pd.textContent=it.probeDetail+(it.latency_ms!=null?' · '+it.latency_ms+'ms':'');body.appendChild(pd);}
    const stat=document.createElement('span');stat.className='apistat';stat.style.color=col;stat.textContent=lab;
    row.append(dot,body,stat); list.appendChild(row);
  });
  return list;
}
function openAllApis(hl){
  openGroupId='__all__'; openGroupHl=hl||null;
  const items=allApiItems();
  const h=countHealth();
  $('p-code').textContent='ALL APIs';
  $('p-name').textContent='Every endpoint across all '+GROUP_ORDER.length+' groups';
  const st=$('p-status');
  const health=h.down?'down':(h.warn?'warn':'ok');
  const cmap={ok:['HEALTHY',HC.ok],warn:['DEGRADED',HC.warn],down:['DOWN',HC.down]};
  const c=cmap[health]||cmap.ok;
  st.textContent='● '+c[0]+' · '+items.length+' total · '+h.down+' down';
  st.style.color=c[1];st.style.background=c[1]+'22';st.style.border='1px solid '+c[1]+'55';
  const bodyEl=$('p-body');
  bodyEl.innerHTML='';
  const sect=document.createElement('div');
  sect.className='sect';
  sect.textContent='ALL GROUPS ('+items.length+') — down/warn first · then M# ascending';
  bodyEl.appendChild(sect);
  bodyEl.appendChild(renderApiList(items,hl,true));
  bodyEl.scrollTop=0;
  hideFabricObservability();
  $('panel').classList.add('open');
}
function openGroupBox(id,hl){
  openGroupId=id; openGroupHl=hl||null;
  const items=groupItems(id);
  if(!items.length)return;
  const [title,sub]=groupTitle(id);
  const anyDown=items.some(i=>i.health==='down'||i.health==='crit');
  const anyWarn=items.some(i=>i.health==='warn');
  const health=anyDown?'down':(anyWarn?'warn':'ok');
  const downN=items.filter(i=>i.health==='down'||i.health==='crit').length;
  const warnN=items.filter(i=>i.health==='warn').length;
  $('p-code').textContent=title;
  $('p-name').textContent=sub;
  const st=$('p-status'),cmap={ok:['HEALTHY',HC.ok],warn:['DEGRADED',HC.warn],crit:['CRITICAL',HC.crit],down:['DOWN',HC.down]};
  const c=cmap[health]||cmap.ok;
  st.textContent='● '+c[0]+' · '+items.length+' listed';
  st.style.color=c[1];st.style.background=c[1]+'22';st.style.border='1px solid '+c[1]+'55';
  const bodyEl=$('p-body');
  bodyEl.innerHTML='';
  const sect=document.createElement('div');
  sect.className='sect';
  sect.textContent=title+' ('+items.length+') — down/warn first · then M# ascending';
  bodyEl.appendChild(sect);
  bodyEl.appendChild(renderApiList(items,hl));
  if(downN){
    const a=document.createElement('div');a.className='sect';a.style.color='var(--down)';a.textContent='Alert';bodyEl.appendChild(a);
    const t=document.createElement('div');t.style.cssText='font-family:var(--mono);font-size:11.5px;color:#FFC2C9;line-height:1.6';
    t.textContent=downN+' endpoint(s) DOWN — blinking on the map.'; bodyEl.appendChild(t);
  }
  if(warnN){
    const a=document.createElement('div');a.className='sect';a.style.color='var(--warn)';a.textContent='Degraded';bodyEl.appendChild(a);
    const t=document.createElement('div');t.style.cssText='font-family:var(--mono);font-size:11.5px;color:#FFE2A8;line-height:1.6';
    t.textContent=warnN+' endpoint(s) in WARN state.'; bodyEl.appendChild(t);
  }
  bodyEl.scrollTop=0;
  hideFabricObservability();
  $('panel').classList.add('open');
}

/* ===== container ===== */
const C=CFG.container;
const containerG=el('g',{class:'nodeRect','data-id':'container'});
Lcore.appendChild(containerG);
const containerRect=panel(containerG,{x:C.x+C.w/2,y:C.y,w:C.w,h:C.h,rx:24,fill:'url(#gContainer)',stroke:'rgba(110,139,255,.5)',sw:1.8});
const containerLblL=label(containerG,C.x+24,C.y+24,C.label,{anchor:'start',size:12,ls:3,fill:'var(--indigo-2)',font:'var(--disp)',weight:600});
const containerLblR=label(containerG,C.x+C.w-24,C.y+24,'6E · OCP',{anchor:'end',size:11,fill:'var(--cyan)'});

/* ===== MF (own box, above MS) ===== */
const MF=CFG.mf;
(function(){
  const g=el('g',{class:'nodeRect'});g.dataset.id='MF';
  panel(g,{x:MF.x,y:MF.y,w:MF.w,h:MF.h,rx:11,stroke:'var(--indigo-2)'});
  g.appendChild(el('circle',{cx:MF.x-MF.w/2+16,cy:MF.y+MF.h/2,r:4,fill:HC.ok,filter:'url(#glow)'}));
  label(g,MF.x-MF.w/2+30,MF.y+MF.h/2-6,'MF',{anchor:'start',size:16,weight:700,font:'var(--disp)'});
  label(g,MF.x+MF.w/2-14,MF.y+MF.h/2-6,MF.sub,{anchor:'end',size:9,fill:'var(--ink-dim)',ls:1.5});
  monLabel(g,MF.x+MF.w/2-12,MF.y+MF.h-9,MF.mon||CFG.mf.mon,{anchor:'end',size:7.5});
  Lcore.appendChild(g);
  g.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable('MF');return;}e.stopPropagation();showPanel('MF','Mainframe','info',
    row('System','MF')+row('Monitoring',MF.mon||CFG.mf.mon||'M1')+row('Type','Mainframe of record')+row('Feeds','MS · pipeline')+row('Status','operational'));});
})();
NODES.mf={x:MF.x,y:MF.y+MF.h/2,top:{x:MF.x,y:MF.y},bottom:{x:MF.x,y:MF.y+MF.h},left:{x:MF.x-MF.w/2,y:MF.y+MF.h/2},right:{x:MF.x+MF.w/2,y:MF.y+MF.h/2}};

/* ===== MS box ===== */
const H=CFG.hub;
const MS_CELL_UI=[];
(function(){
  const msItems=(CFG.apiGroups&&CFG.apiGroups.ms)||[];
  const msDown=msItems.some(i=>i.health==='down'||i.health==='crit');
  const msWarn=msItems.some(i=>i.health==='warn');
  const hubG=el('g',{class:'nodeRect'}); hubG.dataset.id='MS-HUB';
  const hubRect=panel(hubG,{x:H.x,y:H.y,w:H.w,h:H.h,fill:'url(#gHub)',stroke:'rgba(110,139,255,.5)',rx:16,sw:1.4});
  const hdrL=H.x-H.w/2+14,hdrR=H.x+H.w/2-14;
  label(hubG,hdrL,H.y+16,H.label,{anchor:'start',size:13,ls:4,fill:'var(--indigo-2)',font:'var(--disp)',weight:700});
  const msDot=el('circle',{cx:hdrR-8,cy:H.y+16,r:4,fill:msDown?HC.down:(msWarn?HC.warn:HC.ok),filter:'url(#glow)'});
  hubG.appendChild(msDot);
  label(hubG,hdrR-18,H.y+16,(msItems.length?msItems.length+' svc · tap':'microservices'),{anchor:'end',size:9,fill:'var(--ink-dim)'});
  const cellMonR=(CFG.ms||[]).map(m=>Array.isArray(m)?m[2]:'').filter(Boolean);
  const cellLo=cellMonR.length?cellMonR[0]:'';
  const cellHi=cellMonR.length?cellMonR[cellMonR.length-1]:'';
  const cellRange=cellLo&&(cellHi!==cellLo?cellLo+' → '+cellHi:cellLo);
  const msMonR=(CFG.groupMon&&CFG.groupMon.ms)||'';
  const hdrMon=cellRange+(cellRange&&msMonR?' · ':'')+(msMonR&&msMonR!==cellRange?msMonR:'');
  if(hdrMon)monLabel(hubG,hdrL,H.y+32,hdrMon,{anchor:'start',size:7});
  Lcore.appendChild(hubG);
  hubG.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable('MS-HUB');return;}e.stopPropagation();if(msItems.length)openGroupBox('ms');});
  GROUP_UI.ms={g:hubG,panel:hubRect,dot:msDot,baseColor:'rgba(110,139,255,.5)'};
  const cols=3,padx=16,gw=(H.w-padx*2)/cols,gh=30,rowPitch=gh+20,y0=H.y+58;
  const mstip=$('mstip');
  window.showMsTip=function(e,shortName,fullName){
    mstip.innerHTML='<span class="short">'+shortName+'</span><span class="full">'+fullName+'</span>';
    mstip.classList.add('show');
    mstip.style.left=(e.clientX+14)+'px';
    mstip.style.top=(e.clientY-36)+'px';
  };
  window.hideMsTip=function(){mstip.classList.remove('show');};
  function openMSCell(shortName,fullName,monId){
    const item=msItems.find(i=>i.name===fullName);
    const health=item?item.health:'ok';
    const addr=item&&item.address?item.address:'OpenShift · OCP';
    const mon=item?itemMon(item):monId;
    showPanel(shortName,fullName,health,
      row('Short code',shortName)+row('Monitoring',mon||'—')+row('Microservice',fullName)+row('Runtime',addr)+
      row('Cluster','ocpintprdclu')+
      `<div class="sect">Actions</div><div class="chips"><span class="chip" style="cursor:pointer" id="ms-viewall">View all MS APIs</span></div>`);
    $('ms-viewall').onclick=ev=>{ev.stopPropagation();openGroupBox('ms',fullName.toUpperCase());};
  }
  CFG.ms.forEach((m,i)=>{
    const shortName=Array.isArray(m)?m[0]:m;
    const fullName=Array.isArray(m)?m[1]:m;
    const monId=Array.isArray(m)&&m[2]?m[2]:'';
    const c=i%cols,r=Math.floor(i/cols);
    const cx=H.x-H.w/2+padx+gw*c+gw/2, cy=y0+r*rowPitch+gh/2;
    const g=el('g',{class:'nodeRect'});g.dataset.id='MS:'+fullName;g.dataset.short=shortName;g.dataset.mon=monId;
    const cellRect=el('rect',{x:cx-gw/2+3,y:cy-gh/2,width:gw-6,height:gh,rx:7,fill:'rgba(46,123,255,.18)',stroke:'rgba(110,139,255,.4)','stroke-width':1});
    g.appendChild(cellRect);
    const t=el('text',{x:cx,y:cy,'text-anchor':'middle','dominant-baseline':'middle','font-size':shortName.length>6?9:11,fill:'var(--ink)','font-weight':600});t.textContent=shortName;
    g.appendChild(t);
    const monT=monLabel(g,cx,cy+gh/2+9,monId,{size:7});
    MS_CELL_UI.push({id:'MS:'+fullName,g,cx,cy,gw,gh,cellRect,t,monT});
    Lcore.appendChild(g);
    g.addEventListener('pointerenter',e=>{if(editMode||dragging)return;showMsTip(e,shortName,fullName);});
    g.addEventListener('pointermove',e=>{if(mstip.classList.contains('show')){mstip.style.left=(e.clientX+14)+'px';mstip.style.top=(e.clientY-36)+'px';}});
    g.addEventListener('pointerleave',hideMsTip);
    g.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable('MS:'+fullName);return;}e.stopPropagation();hideMsTip();openMSCell(shortName,fullName,monId);});
  });
})();
NODES.hub={x:H.x,y:H.y+H.h/2,top:{x:H.x,y:H.y},right:{x:H.x+H.w/2,y:H.y+H.h/2},bottom:{x:H.x,y:H.y+H.h}};
/* MF -> MS link */
const mfMsLink=el('path',{fill:'none',stroke:'rgba(110,139,255,.65)','stroke-width':2.2,filter:'url(#glow)'});
Llinks.appendChild(mfMsLink);

/* ===== data stores (mongo/aims) — cylinder icons below MS ===== */
CFG.spine.forEach(s=>{
  const g=el('g',{class:'nodeRect db-node'});g.dataset.id=s.id;
  const store=(CFG.dataStores&&CFG.dataStores[s.id])||[];
  const anyDown=store.some(i=>i.health==='down'||i.health==='crit');
  const cx=s.x,cy=s.y+s.h/2,rx=s.w/2;
  const strokes=dbCylinder(g,cx,s.y,s.w,s.h,s.color,anyDown);
  g.appendChild(el('rect',{x:cx-rx-4,y:s.y-4,width:s.w+8,height:s.h+36,fill:'transparent',stroke:'none'}));
  const spineDot=el('circle',{cx:cx-rx+10,cy:s.y+s.h+26,r:4,fill:anyDown?HC.down:HC.ok,filter:'url(#glow)'});
  g.appendChild(spineDot);
  const lbl=label(g,cx,s.y+s.h+14,s.label,{size:13,weight:600,font:'var(--disp)'});
  const sub=label(g,cx,s.y+s.h+28,s.sub,{size:9,fill:'var(--ink-dim)'});
  GROUP_UI[s.id]={g,strokes,dot:spineDot,baseColor:s.color,lbl,sub};
  monLabel(g,cx,s.y+s.h+42,s.mon,{size:7.5});
  Lcore.appendChild(g);
  NODES[s.id]={x:cx,y:cy,top:{x:cx,y:s.y},bottom:{x:cx,y:s.y+s.h},left:{x:cx-rx,y:cy},right:{x:cx+rx,y:cy},meta:{label:s.label,sub:s.sub,kind:'Data layer'}};
  g.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable(s.id);return;}e.stopPropagation();
    if(store.length){openGroupBox(s.id);return;}
    openNode(s.id);});
});

/* ===== collapsed API group boxes (label only on map; full list in side panel) ===== */
(CFG.groupBoxes||[]).forEach(box=>{
  const items=groupItems(box.id);
  const anyDown=items.some(i=>i.health==='down'||i.health==='crit');
  const anyWarn=items.some(i=>i.health==='warn');
  const dn=items.filter(i=>i.health==='down'||i.health==='crit').length;
  const wn=items.filter(i=>i.health==='warn').length;
  const g=el('g',{class:'nodeRect'});g.dataset.id=box.id;
  const boxRect=panel(g,{x:box.x,y:box.y,w:box.w,h:box.h,rx:13,stroke:anyDown?'rgba(255,59,78,.65)':(anyWarn?'rgba(255,194,75,.55)':box.color),sw:anyDown?1.8:1.3});
  let blinkRect=null;
  if(anyDown) blinkRect=g.appendChild(el('rect',{x:box.x-box.w/2,y:box.y,width:box.w,height:box.h,rx:13,fill:'none',stroke:'#FF3B4E','stroke-width':2,class:'blink'}));
  const dot=el('circle',{cx:box.x-box.w/2+18,cy:box.y+box.h/2,r:5,fill:anyDown?HC.down:(anyWarn?HC.warn:HC.ok),filter:'url(#glow)'});
  if(anyDown)dot.setAttribute('class','blink'); g.appendChild(dot);
  const title=label(g,box.x-box.w/2+34,box.y+box.h/2-10,box.label,{anchor:'start',size:13,weight:700,font:'var(--disp)',fill:anyDown?'#FF8A98':(anyWarn?'#FFE2A8':'var(--ink)')});
  let hintTxt=items.length+' APIs · tap to view';
  if(anyDown) hintTxt=dn+' of '+items.length+' down · tap to view';
  else if(anyWarn) hintTxt=wn+' of '+items.length+' warn · tap to view';
  if(box.monRange) hintTxt=box.monRange+' · '+hintTxt;
  const hint=label(g,box.x-box.w/2+34,box.y+box.h/2+4,hintTxt,{anchor:'start',size:9,fill:'var(--ink-dim)'});
  const chevron=label(g,box.x+box.w/2-16,box.y+box.h/2,'▸',{anchor:'end',size:16,fill:'var(--ink-dim)'});
  GROUP_UI[box.id]={g,panel:boxRect,dot,blinkRect,title,hint,chevron,baseColor:box.color};
  Lcore.appendChild(g);
  NODES[box.id]={x:box.x,y:box.y+box.h/2,top:{x:box.x,y:box.y},bottom:{x:box.x,y:box.y+box.h},left:{x:box.x-box.w/2,y:box.y+box.h/2},right:{x:box.x+box.w/2,y:box.y+box.h/2},meta:{label:box.label,sub:box.sub,kind:'API group'}};
  g.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable(box.id);return;}e.stopPropagation();openGroupBox(box.id);});
});

/* ===== internal flow links + particles ===== */
const flowSegs=[];
const STATIC_LINKS=[];
function bez(p0,p1,p2,p3,t){const u=1-t;return{
  x:u*u*u*p0.x+3*u*u*t*p1.x+3*u*t*t*p2.x+t*t*t*p3.x,
  y:u*u*u*p0.y+3*u*u*t*p1.y+3*u*t*t*p2.y+t*t*t*p3.y};}
function refreshFlowSeg(s){
  const a=s.getA(),b=s.getB(); if(!a||!b)return;
  s.a=a;s.b=b;
  if(s.kind==='bez'){
    s.c1={x:(a.x+b.x)/2,y:a.y};s.c2={x:(a.x+b.x)/2,y:b.y};
    const d=`M ${a.x} ${a.y} C ${s.c1.x} ${s.c1.y}, ${s.c2.x} ${s.c2.y}, ${b.x} ${b.y}`;
    s.paths.forEach(p=>p.setAttribute('d',d));
  }else if(s.kind==='spine'){
    const dx=Math.abs(a.x-b.x),dy=Math.abs(a.y-b.y);
    s.c1=dy>=dx?{x:(a.x+b.x)/2,y:a.y}:{x:a.x,y:(a.y+b.y)/2};
    s.c2=dy>=dx?{x:(a.x+b.x)/2,y:b.y}:{x:b.x,y:(a.y+b.y)/2};
    const d=`M ${a.x} ${a.y} C ${s.c1.x} ${s.c1.y}, ${s.c2.x} ${s.c2.y}, ${b.x} ${b.y}`;
    s.paths.forEach(p=>p.setAttribute('d',d));
    if(s.lbl&&s.labelEls){const lx=s.lblPos?.x??(a.x+b.x)/2,ly=s.lblPos?.y??((a.y+b.y)/2);
      const fs=10,padX=9,padY=5,w=Math.max(s.lbl.length*5.8+padX*2,48),h=fs+padY*2;
      s.labelEls.rect.setAttribute('x',lx-w/2);s.labelEls.rect.setAttribute('y',ly-h/2);
      s.labelEls.rect.setAttribute('width',w);s.labelEls.rect.setAttribute('height',h);
      s.labelEls.text.setAttribute('x',lx);s.labelEls.text.setAttribute('y',ly);}
  }
}
function refreshAllFlows(){
  flowSegs.forEach(refreshFlowSeg);
  STATIC_LINKS.forEach(l=>{const a=l.getA(),b=l.getB();if(a&&b)l.path.setAttribute('d',`M ${a.x} ${a.y} L ${b.x} ${b.y}`);});
}
function flowLink(getA,getB,color,spd){
  const paths=[
    Llinks.appendChild(el('path',{fill:'none',stroke:color,opacity:.18,'stroke-width':12})),
    Llinks.appendChild(el('path',{fill:'none',stroke:color,'stroke-width':2.6,opacity:.88,filter:'url(#glow)'}))
  ];
  const dot=el('circle',{r:3.6,fill:color.replace(/[\d.]+\)$/,'1)'),filter:'url(#glow)'});Lpart.appendChild(dot);
  const seg={kind:'bez',getA,getB,paths,dot,t:Math.random(),speed:spd||0.6,a:null,b:null,c1:null,c2:null};
  flowSegs.push(seg);refreshFlowSeg(seg);
}
function linkLabel(p,x,y,txt){
  const fs=10,padX=9,padY=5,w=Math.max(txt.length*5.8+padX*2,48),h=fs+padY*2;
  const rect=p.appendChild(el('rect',{x:x-w/2,y:y-h/2,width:w,height:h,rx:6,fill:'rgba(8,14,36,.94)',stroke:'rgba(110,160,255,.55)','stroke-width':1.2}));
  const text=el('text',{x,y,'text-anchor':'middle','dominant-baseline':'middle','font-size':fs,fill:'#F0F6FF','font-weight':700,'font-family':'var(--mono)','letter-spacing':.3});
  text.textContent=txt;p.appendChild(text);return{rect,text};
}
function spineFlowLink(getA,getB,color,lbl,pos){
  const paths=[
    Llinks.appendChild(el('path',{fill:'none',stroke:color,opacity:.32,'stroke-width':16})),
    Llinks.appendChild(el('path',{fill:'none',stroke:color,'stroke-width':5.5,opacity:1,filter:'url(#glow)'})),
    Llinks.appendChild(el('path',{fill:'none',stroke:'#E8F4FF','stroke-width':2,opacity:.92,'stroke-dasharray':'10 7'}))
  ];
  const dots=[];
  for(let i=0;i<3;i++){const dot=el('circle',{r:i?3.6:5,fill:'#6AE8FF',filter:'url(#glow)'});Lpart.appendChild(dot);dots.push(dot);}
  const lx=pos?.x??0,ly=pos?.y??0;
  const labelEls=lbl?linkLabel(LlinkLbl,lx,ly,lbl):null;
  const seg={kind:'spine',getA,getB,paths,dots,lbl,lblPos:pos,labelEls,t:Math.random(),speed:1.05,a:null,b:null,c1:null,c2:null};
  dots.forEach((dot,i)=>{flowSegs.push({...seg,dot,speed:1.05+i*0.18,t:Math.random()});});
  refreshFlowSeg(seg);
}
STATIC_LINKS.push({path:mfMsLink,getA:()=>({x:MF.x,y:MF.y+MF.h}),getB:()=>({x:H.x,y:H.y})});
spineFlowLink(()=>NODES.hub?.bottom,()=>NODES.mongo?.top,'rgba(46,123,255,.95)','MS → MongoDB',{x:612,y:754});
if(NODES.aims&&NODES.sp)spineFlowLink(()=>NODES.aims.right,()=>NODES.sp.left,'rgba(89,224,255,.95)','AIMS DB → SP',{x:920,y:640});
/* MongoDB hub — feeds MF, MS (labelled spine link above), and every API group */
if(NODES.mongo){
  const mongoCol='rgba(46,123,255,.72)';
  if(NODES.mf)flowLink(()=>NODES.mongo.left,()=>NODES.mf.left,mongoCol,0.48);
  const boxes=CFG.groupBoxes||[];
  boxes.forEach((box,i)=>{
    const frac=boxes.length>1?i/(boxes.length-1):0.5;
    flowLink(()=>{
      const m=NODES.mongo;if(!m)return null;
      return{x:m.right.x,y:m.top.y+(m.bottom.y-m.top.y)*frac};
    },()=>NODES[box.id]?.left,mongoCol,0.38+i*0.03);
  });
}
for(let i=0;i<(CFG.groupBoxes||[]).length-1;i++){
  const idA=CFG.groupBoxes[i].id,idB=CFG.groupBoxes[i+1].id;
  flowLink(()=>NODES[idA]?.bottom,()=>NODES[idB]?.top,'rgba(79,139,255,.72)');
}
refreshAllFlows();

/* ===== floating apps ===== */
const PLANETS=[];
function borderPoint(px,py){
  const dx=px-CFG.CX,dy=py-CFG.CY,hw=C.w/2,hh=C.h/2;
  const tx=Math.abs(dx)>1?hw/Math.abs(dx):1e9, ty=Math.abs(dy)>1?hh/Math.abs(dy):1e9, t=Math.min(tx,ty);
  return {x:CFG.CX+dx*t,y:CFG.CY+dy*t};
}
(function(){
  const inner=CFG.apps.filter(a=>a[2]===0), outer=CFG.apps.filter(a=>a[2]===1);
  function place(list,ring,off){
    list.forEach((a,i)=>{
      const [code,name,,health,addr,monId]=a, ang=(i/list.length)*Math.PI*2+off, speed=ring===0?0.05:-0.032;
      const line=el('path',{fill:'none',stroke:HC[health],'stroke-width':1.1,opacity:.3,class:'applink'});Llinks.appendChild(line);
      const g=el('g',{class:'planet'});g.dataset.code=code;g.dataset.mon=monId||'';
      g.append(
        el('circle',{r:48,fill:HC[health],opacity:.16,filter:'url(#softglow)'}),
        el('circle',{r:34,fill:'url(#gPlanet)',stroke:HC[health],'stroke-width':2.2}),
        el('circle',{r:34,fill:'none',stroke:HC[health],'stroke-width':1.1,opacity:.5,'stroke-dasharray':'3 4'}));
      const t=el('text',{'text-anchor':'middle','dominant-baseline':'middle','font-size':code.length>3?10:13.5,fill:'var(--ink)','font-weight':600,'font-family':'var(--disp)'});t.textContent=code;g.appendChild(t);
      g.appendChild(el('circle',{cx:24,cy:-24,r:5,fill:HC[health],stroke:'#0b1024','stroke-width':1.5,filter:'url(#glow)'}));
      if(monId) monLabel(g,0,40,monId,{dy:0});
      Lplanets.appendChild(g);
      const pkt=el('circle',{r:2.6,fill:HC[health],filter:'url(#glow)'});Lpart.appendChild(pkt);
      const obj={code,name,health,ring,ang,speed,g,line,pkt,pktT:Math.random(),rx:CFG.rings[ring].rx,ry:CFG.rings[ring].ry,x:0,y:0,addr:addr||'',mon:monId||'',fixed:false,r:34};
      PLANETS.push(obj);
      g.addEventListener('click',e=>{if(editMode){e.stopPropagation();selectEditable('planet:'+code);return;}e.stopPropagation();openApp(obj);highlight(code);});
      g.addEventListener('pointerenter',()=>{if(editMode||dragging)return;highlight(code)});
      g.addEventListener('pointerleave',()=>{if(editMode||selected)return;highlight(null)});
    });
  }
  place(inner,0,0);place(outer,1,Math.PI/12);
})();
function updatePlanet(p){
  if(p.fixed&&p.x!=null&&p.y!=null){
    p.g.setAttribute('transform',`translate(${p.x},${p.y})`);
    const bp=borderPoint(p.x,p.y);
    p.line.setAttribute('d',`M ${p.x} ${p.y} L ${bp.x} ${bp.y}`);
    if(flowOn){const t=p.pktT; p.pkt.setAttribute('cx',lerp(p.x,bp.x,t)); p.pkt.setAttribute('cy',lerp(p.y,bp.y,t)); p.pkt.setAttribute('opacity',.9);}
    else p.pkt.setAttribute('opacity',0);
    return;
  }
  p.x=CFG.CX+Math.cos(p.ang)*p.rx; p.y=CFG.CY+Math.sin(p.ang)*p.ry;
  p.g.setAttribute('transform',`translate(${p.x},${p.y})`);
  const bp=borderPoint(p.x,p.y);
  p.line.setAttribute('d',`M ${p.x} ${p.y} L ${bp.x} ${bp.y}`);
  if(flowOn){const t=p.pktT; p.pkt.setAttribute('cx',lerp(p.x,bp.x,t)); p.pkt.setAttribute('cy',lerp(p.y,bp.y,t)); p.pkt.setAttribute('opacity',.9);}
  else p.pkt.setAttribute('opacity',0);
}

/* animation */
PLANETS.forEach(updatePlanet);
let last=performance.now();
function loop(now){
  const dt=Math.min(.05,(now-last)/1000);last=now;
  PLANETS.forEach(p=>{if(orbitOn)p.ang+=p.speed*dt; if(flowOn)p.pktT=(p.pktT+dt*.55)%1; updatePlanet(p);});
  flowSegs.forEach(s=>{ if(flowOn){s.t=(s.t+dt*(s.speed||0.6))%1; const q=bez(s.a,s.c1,s.c2,s.b,s.t); s.dot.setAttribute('cx',q.x);s.dot.setAttribute('cy',q.y);s.dot.setAttribute('opacity',.9);} else s.dot.setAttribute('opacity',0);});
  requestAnimationFrame(loop);
}
requestAnimationFrame(loop);

function highlight(code){
  if(!code){PLANETS.forEach(p=>{p.g.classList.remove('dim','hot');p.line.setAttribute('opacity',.3);p.line.setAttribute('stroke-width',1.1);});return;}
  PLANETS.forEach(p=>{const on=p.code===code;p.g.classList.toggle('dim',!on);p.g.classList.toggle('hot',on);
    p.line.setAttribute('opacity',on?.95:.06);p.line.setAttribute('stroke-width',on?2.4:1.1);});
}

/* detail panel */
const panelEl=$('panel');
function hideFabricObservability(){
  const m=$('metrics');
  if(!m)return;
  m.classList.remove('open');
  m.classList.add('metrics-hidden');
}
function restoreFabricObservability(){
  const m=$('metrics');
  if(m)m.classList.remove('metrics-hidden');
}
function closeDetailPanel(){
  panelEl.classList.remove('open');
  openGroupId=null;openGroupHl=null;selected=null;
  highlight(null);hideMsTip();
  restoreFabricObservability();
}
function showPanel(code,name,health,extra){
  $('p-code').textContent=code;$('p-name').textContent=name;
  const st=$('p-status'),cmap={ok:['HEALTHY',HC.ok],warn:['DEGRADED',HC.warn],crit:['CRITICAL',HC.crit],down:['DOWN',HC.down],info:['ACTIVE','#59E0FF']},c=cmap[health]||cmap.info;
  st.textContent='● '+c[0];st.style.color=c[1];st.style.background=c[1]+'22';st.style.border='1px solid '+c[1]+'55';
  $('p-body').innerHTML=extra;
  hideFabricObservability();
  panelEl.classList.add('open');
}
const row=(k,v)=>`<div class="kv"><span class="k">${k}</span><span class="v">${v}</span></div>`;
const rnd=(a,b,d=0)=>R(a,b).toFixed(d);
function openApp(p){
  selected=p.code;highlight(p.code);
  const err=p.health==='crit'?rnd(4,9,2):p.health==='warn'?rnd(1,3,2):rnd(0,.4,2);
  showPanel(p.code,p.name,p.health,
    row('App code',p.code)+(p.mon?row('Monitoring',p.mon):'')+row('Domain','Operations')+(p.addr?row('Module',p.addr):'')+row('Throughput',rnd(20,900)+' msg/s')+
    row('p95 latency',rnd(8,140)+' ms')+row('Error rate',err+' %')+
    row('Replicas',Math.floor(R(2,6))+'/'+Math.ceil(R(4,8)))+row('Cluster',p.ring?'ocpintprdclu2':'ocpintprdclu')+
    `<div class="sect">Health</div><div class="barwrap"><div class="bar" style="width:${p.health==='crit'?38:p.health==='warn'?72:96}%;background:${HC[p.health]}"></div></div>`+
    `<div class="sect">Reaches</div><div class="chips">${['MS','MongoDB','AIMS DB','External API','Internal API'].map(c=>`<span class="chip">${c}</span>`).join('')}</div>`);
}
function openNode(id){
  const m=NODES[id].meta; let b=row('Type',m.kind)+row('Status','operational');
  b+=row('Latency',rnd(2,40)+' ms')+row('Ops/s',rnd(50,1200));
  showPanel(m.label||id,m.kind,'info',b);
}
function openMS(m){openGroupBox('ms',m.toUpperCase());}
$('pclose').onclick=e=>{e.stopPropagation();closeDetailPanel();};
svg.addEventListener('click',()=>{if(dragging||editMode)return;closeDetailPanel();});

/* ===== layout edit mode ===== */
const EDIT_REG=new Map();
const editOutline=el('rect',{class:'edit-outline'});
const editHandlesG=el('g',{id:'edit-handles'});
LeditUi.append(editOutline,editHandlesG);
const HANDLE_NAMES=['nw','n','ne','e','se','s','sw','w'];
const editHandles=Object.fromEntries(HANDLE_NAMES.map(n=>[n,el('rect',{class:'edit-handle '+n,width:10,height:10,rx:2,'data-handle':n})]));
HANDLE_NAMES.forEach(n=>editHandlesG.appendChild(editHandles[n]));

function svgPoint(clientX,clientY){
  const r=svg.getBoundingClientRect();
  const sx=(clientX-r.left)/r.width*VB[2],sy=(clientY-r.top)/r.height*VB[3];
  return{x:(sx-view.x)/view.k,y:(sy-view.y)/view.k};
}
function setNodeMF(b){
  Object.assign(MF,b);
  const g=document.querySelector('[data-id="MF"]'); if(!g)return;
  const rect=g.querySelector('rect'); if(!rect)return;
  rect.setAttribute('x',b.x-b.w/2);rect.setAttribute('y',b.y);rect.setAttribute('width',b.w);rect.setAttribute('height',b.h);
  const dot=g.querySelector('circle');if(dot){dot.setAttribute('cx',b.x-b.w/2+16);dot.setAttribute('cy',b.y+b.h/2);}
  const texts=g.querySelectorAll('text');
  if(texts[0]){texts[0].setAttribute('x',b.x-b.w/2+30);texts[0].setAttribute('y',b.y+b.h/2-6);}
  if(texts[1]){texts[1].setAttribute('x',b.x+b.w/2-14);texts[1].setAttribute('y',b.y+b.h/2-6);}
  const mon=g.querySelector('.mon-tag');if(mon){mon.setAttribute('x',b.x+b.w/2-12);mon.setAttribute('y',b.y+b.h-9);}
  NODES.mf={x:MF.x,y:MF.y+MF.h/2,top:{x:MF.x,y:MF.y},bottom:{x:MF.x,y:MF.y+MF.h},left:{x:MF.x-MF.w/2,y:MF.y+MF.h/2},right:{x:MF.x+MF.w/2,y:MF.y+MF.h/2}};
}
function setNodeHub(b){
  Object.assign(H,b);
  const ui=GROUP_UI.ms; if(!ui||!ui.panel||!ui.g)return;
  ui.panel.setAttribute('x',b.x-b.w/2);ui.panel.setAttribute('y',b.y);ui.panel.setAttribute('width',b.w);ui.panel.setAttribute('height',b.h);
  const hdrL=b.x-b.w/2+14,hdrR=b.x+b.w/2-14;
  const texts=ui.g.querySelectorAll('text');
  if(texts[0]){texts[0].setAttribute('x',hdrL);texts[0].setAttribute('y',b.y+16);}
  if(texts[1]){texts[1].setAttribute('x',hdrR-18);texts[1].setAttribute('y',b.y+16);}
  if(ui.dot){ui.dot.setAttribute('cx',hdrR-8);ui.dot.setAttribute('cy',b.y+16);}
  const mon=ui.g.querySelector('.mon-tag');if(mon){mon.setAttribute('x',hdrL);mon.setAttribute('y',b.y+32);}
  NODES.hub={x:H.x,y:H.y+H.h/2,top:{x:H.x,y:H.y},right:{x:H.x+H.w/2,y:H.y+H.h/2},bottom:{x:H.x,y:H.y+H.h}};
}
function setNodeContainer(b){
  Object.assign(C,b);
  containerRect.setAttribute('x',b.x);containerRect.setAttribute('y',b.y);containerRect.setAttribute('width',b.w);containerRect.setAttribute('height',b.h);
  containerLblL.setAttribute('x',b.x+24);containerLblL.setAttribute('y',b.y+24);
  containerLblR.setAttribute('x',b.x+b.w-24);containerLblR.setAttribute('y',b.y+24);
}
function setNodeGroupBox(id,b){
  const box=(CFG.groupBoxes||[]).find(x=>x.id===id); if(!box)return;
  Object.assign(box,b);
  const ui=GROUP_UI[id]; if(!ui)return;
  ui.panel.setAttribute('x',b.x-b.w/2);ui.panel.setAttribute('y',b.y);ui.panel.setAttribute('width',b.w);ui.panel.setAttribute('height',b.h);
  if(ui.blinkRect){ui.blinkRect.setAttribute('x',b.x-b.w/2);ui.blinkRect.setAttribute('y',b.y);ui.blinkRect.setAttribute('width',b.w);ui.blinkRect.setAttribute('height',b.h);}
  ui.dot.setAttribute('cx',b.x-b.w/2+18);ui.dot.setAttribute('cy',b.y+b.h/2);
  if(ui.title){ui.title.setAttribute('x',b.x-b.w/2+34);ui.title.setAttribute('y',b.y+b.h/2-10);}
  if(ui.hint){ui.hint.setAttribute('x',b.x-b.w/2+34);ui.hint.setAttribute('y',b.y+b.h/2+4);}
  if(ui.chevron){ui.chevron.setAttribute('x',b.x+b.w/2-16);ui.chevron.setAttribute('y',b.y+b.h/2);}
  NODES[id]={x:box.x,y:box.y+box.h/2,top:{x:box.x,y:box.y},bottom:{x:box.x,y:box.y+box.h},left:{x:box.x-box.w/2,y:box.y+box.h/2},right:{x:box.x+box.w/2,y:box.y+box.h/2},meta:NODES[id]?.meta};
}
function setNodeSpine(id,b){
  const s=(CFG.spine||[]).find(x=>x.id===id); if(!s)return;
  if(s._ox==null){s._ox=s.x;s._oy=s.y;}
  Object.assign(s,b);
  const ui=GROUP_UI[id]; if(!ui)return;
  ui.g.setAttribute('transform',`translate(${s.x-s._ox},${s.y-s._oy})`);
  const cx=s.x+s.w/2,cy=s.y+s.h/2,rx=s.w/2;
  NODES[id]={x:cx,y:cy,top:{x:cx,y:s.y},bottom:{x:cx,y:s.y+s.h},left:{x:cx-rx,y:cy},right:{x:cx+rx,y:cy},meta:NODES[id]?.meta};
}
function setNodeMsCell(cell,b){
  cell.cx=b.cx;cell.cy=b.cy;cell.gw=b.w;cell.gh=b.h;
  const hw=b.w/2,hh=b.h/2;
  cell.cellRect.setAttribute('x',b.cx-hw+3);cell.cellRect.setAttribute('y',b.cy-hh);cell.cellRect.setAttribute('width',b.w-6);cell.cellRect.setAttribute('height',b.h);
  cell.t.setAttribute('x',b.cx);cell.t.setAttribute('y',b.cy);
  if(cell.monT){cell.monT.setAttribute('x',b.cx);cell.monT.setAttribute('y',b.cy+hh+9);}
}
function setNodePlanet(code,b){
  const p=PLANETS.find(x=>x.code===code); if(!p)return;
  p.x=b.cx;p.y=b.cy;p.r=b.r||p.r;p.fixed=true;
  p.g.querySelectorAll('circle').forEach((c,i)=>{if(i===0)c.setAttribute('r',b.r+14);else if(i===1||i===2)c.setAttribute('r',b.r);});
  updatePlanet(p);
}
function registerEditable(spec){EDIT_REG.set(spec.id,spec);}
function initEditRegistry(){
  registerEditable({id:'container',label:'Container',type:'rect',g:containerG,resizable:true,
    getBounds:()=>({x:C.x,y:C.y,w:C.w,h:C.h}),setBounds:setNodeContainer});
  registerEditable({id:'MF',label:'Mainframe',type:'rect',g:document.querySelector('[data-id="MF"]'),resizable:true,
    getBounds:()=>({cx:MF.x,cy:MF.y+MF.h/2,w:MF.w,h:MF.h}),setBounds:b=>setNodeMF({x:b.cx,y:b.cy-b.h/2,w:b.w,h:b.h})});
  registerEditable({id:'MS-HUB',label:'Microservices Hub',type:'rect',g:GROUP_UI.ms?.g,resizable:true,
    getBounds:()=>({cx:H.x,cy:H.y+H.h/2,w:H.w,h:H.h}),setBounds:b=>setNodeHub({x:b.cx,y:b.cy-b.h/2,w:b.w,h:b.h})});
  MS_CELL_UI.forEach(cell=>registerEditable({id:cell.id,label:cell.id.replace('MS:',''),type:'rect',g:cell.g,resizable:true,
    getBounds:()=>({cx:cell.cx,cy:cell.cy,w:cell.gw,h:cell.gh}),setBounds:b=>setNodeMsCell(cell,b)}));
  (CFG.spine||[]).forEach(s=>registerEditable({id:s.id,label:s.label,type:'rect',g:GROUP_UI[s.id]?.g,resizable:true,
    getBounds:()=>({x:s.x,y:s.y,w:s.w,h:s.h}),setBounds:b=>setNodeSpine(s.id,b)}));
  (CFG.groupBoxes||[]).forEach(box=>registerEditable({id:box.id,label:box.label,type:'rect',g:GROUP_UI[box.id]?.g,resizable:true,
    getBounds:()=>({cx:box.x,cy:box.y+box.h/2,w:box.w,h:box.h}),setBounds:b=>setNodeGroupBox(box.id,{x:b.cx,y:b.cy-b.h/2,w:b.w,h:b.h})}));
  PLANETS.forEach(p=>registerEditable({id:'planet:'+p.code,label:p.code,type:'planet',g:p.g,resizable:true,
    getBounds:()=>({cx:p.fixed?p.x:CFG.CX+Math.cos(p.ang)*p.rx,cy:p.fixed?p.y:CFG.CY+Math.sin(p.ang)*p.ry,r:p.r}),
    setBounds:b=>setNodePlanet(p.code,b)}));
}
initEditRegistry();

function boundsToBox(b){
  if(b.r!=null)return{x:b.cx-b.r,y:b.cy-b.r,w:b.r*2,h:b.r*2};
  if(b.cx!=null)return{x:b.cx-b.w/2,y:b.cy-b.h/2,w:b.w,h:b.h};
  return{x:b.x,y:b.y,w:b.w,h:b.h};
}
function boxToBounds(box,spec){
  if(spec.type==='planet')return{cx:box.x+box.w/2,cy:box.y+box.h/2,r:box.w/2};
  const b=spec.getBounds();
  if(b.cx!=null)return{cx:box.x+box.w/2,cy:box.y+box.h/2,w:box.w,h:box.h};
  return{x:box.x,y:box.y,w:box.w,h:box.h};
}
function markLayoutDirty(){layoutDirty=true;$('edit-dirty').style.display='inline';}
let persistTimer=null;
function persistLayout(opts={}){
  const data=collectLayout();
  const json=JSON.stringify(data);
  try{localStorage.setItem('occ_layout_v1',json);}catch(e){}
  fetch('/api/layout',{method:'POST',headers:{'Content-Type':'application/json'},body:json}).catch(()=>{});
  savedLayoutSnapshot=json;layoutDirty=false;$('edit-dirty').style.display='none';
  if(opts.toast)showEditToast('Layout saved');
}
function schedulePersistLayout(){
  if(persistTimer)clearTimeout(persistTimer);
  persistTimer=setTimeout(()=>{persistTimer=null;persistLayout();},300);
}
function showEditToast(msg){const t=$('edit-toast');t.textContent=msg;t.classList.add('show');setTimeout(()=>t.classList.remove('show'),2400);}
function updateEditProps(){
  const spec=selectedEditId?EDIT_REG.get(selectedEditId):null;
  const panel=$('edit-props');
  if(!spec||!editMode){panel.classList.remove('show');return;}
  panel.classList.add('show');
  $('edit-props-title').textContent=spec.label||spec.id;
  const b=spec.getBounds(),box=boundsToBox(b);
  $('ep-x').value=Math.round(spec.type==='planet'?b.cx:(b.cx??box.x+box.w/2));
  $('ep-y').value=Math.round(spec.type==='planet'?b.cy:(b.cy??box.y+box.h/2));
  $('ep-w').value=Math.round(box.w);$('ep-h').value=Math.round(box.h);
  $('ep-r-wrap').style.display=spec.type==='planet'?'flex':'none';
  if(spec.type==='planet')$('ep-r').value=Math.round(b.r);
  $('ep-w').parentElement.style.display=spec.type==='planet'?'none':'flex';
  $('ep-h').parentElement.style.display=spec.type==='planet'?'none':'flex';
}
function drawEditChrome(){
  const spec=selectedEditId?EDIT_REG.get(selectedEditId):null;
  if(!spec||!editMode){editOutline.setAttribute('opacity',0);editHandlesG.setAttribute('opacity',0);return;}
  const box=boundsToBox(spec.getBounds());
  editOutline.setAttribute('x',box.x);editOutline.setAttribute('y',box.y);editOutline.setAttribute('width',box.w);editOutline.setAttribute('height',box.h);editOutline.setAttribute('opacity',1);
  if(!spec.resizable){editHandlesG.setAttribute('opacity',0);return;}
  const pts={nw:[box.x,box.y],n:[box.x+box.w/2,box.y],ne:[box.x+box.w,box.y],e:[box.x+box.w,box.y+box.h/2],se:[box.x+box.w,box.y+box.h],s:[box.x+box.w/2,box.y+box.h],sw:[box.x,box.y+box.h],w:[box.x,box.y+box.h/2]};
  HANDLE_NAMES.forEach(n=>{const[x,y]=pts[n];editHandles[n].setAttribute('x',x-5);editHandles[n].setAttribute('y',y-5);});
  editHandlesG.setAttribute('opacity',1);
}
function selectEditable(id){
  if(selectedEditId){const prev=EDIT_REG.get(selectedEditId);if(prev?.g)prev.g.classList.remove('editable-selected');}
  selectedEditId=id;
  const spec=EDIT_REG.get(id);
  if(!spec){updateEditProps();drawEditChrome();return;}
  if(spec.g)spec.g.classList.add('editable-selected');
  updateEditProps();drawEditChrome();
}
function applyBoundsToSelected(raw){
  const spec=EDIT_REG.get(selectedEditId); if(!spec)return;
  let b;
  if(spec.type==='planet')b={cx:+raw.cx,cy:+raw.cy,r:+raw.r};
  else if(raw.x!=null&&!raw.cx)b=raw;
  else b={cx:+raw.cx,cy:+raw.cy,w:Math.max(20,+raw.w),h:Math.max(16,+raw.h)};
  spec.setBounds(b);markLayoutDirty();updateEditProps();drawEditChrome();refreshAllFlows();schedulePersistLayout();
}
function collectLayout(){
  const elements={};
  EDIT_REG.forEach((spec,id)=>{elements[id]=spec.getBounds();});
  return{version:1,savedAt:new Date().toISOString(),elements};
}
function applyLayoutElements(elements){
  if(!elements)return;
  Object.entries(elements).forEach(([id,b])=>{const spec=EDIT_REG.get(id);if(spec)spec.setBounds(b);});
  drawEditChrome();refreshAllFlows();
}
const defaultElements=JSON.parse(JSON.stringify(collectLayout().elements));
function resetLayout(){
  if(!confirm('Reset all positions to the original layout?'))return;
  if(persistTimer){clearTimeout(persistTimer);persistTimer=null;}
  (CFG.spine||[]).forEach(s=>{delete s._ox;delete s._oy;const ui=GROUP_UI[s.id];if(ui?.g)ui.g.removeAttribute('transform');});
  PLANETS.forEach(p=>{p.fixed=false;p.x=null;p.y=null;});
  Object.entries(defaultElements).forEach(([id,b])=>{const spec=EDIT_REG.get(id);if(spec&&spec.type!=='planet')spec.setBounds(b);});
  PLANETS.forEach(updatePlanet);
  refreshAllFlows();
  persistLayout();
  showEditToast('Layout reset to default');
  if(editMode&&selectedEditId){updateEditProps();drawEditChrome();}
}
async function loadSavedLayout(){
  let server=null,local=null;
  try{const r=await fetch('/api/layout');if(r.ok)server=await r.json();}catch(e){}
  try{const ls=localStorage.getItem('occ_layout_v1');if(ls)local=JSON.parse(ls);}catch(e){}
  const ts=d=>Date.parse(d?.savedAt||0)||0;
  let data=null;
  if(server?.elements&&Object.keys(server.elements).length&&local?.elements&&Object.keys(local.elements).length)
    data=ts(server)>=ts(local)?server:local;
  else if(server?.elements&&Object.keys(server.elements).length)data=server;
  else if(local?.elements&&Object.keys(local.elements).length)data=local;
  if(data?.elements){try{applyLayoutElements(data.elements);savedLayoutSnapshot=JSON.stringify(data);}catch(e){console.warn('layout load skipped',e);}}
}
function saveLayout(){persistLayout({toast:true});}
function setEditMode(on){
  editMode=on;
  document.body.classList.toggle('edit-mode',on);
  $('b-edit').classList.toggle('active',on);
  $('b-save-edit').style.display=on?'inline-block':'none';
  $('b-reset-layout').style.display=on?'inline-block':'none';
  $('b-cancel-edit').style.display=on?'inline-block':'none';
  if(on){savedLayoutSnapshot=JSON.stringify(collectLayout());closeDetailPanel();selectEditable(selectedEditId||'MF');}
  else{if(layoutDirty)persistLayout();if(selectedEditId){const s=EDIT_REG.get(selectedEditId);if(s?.g)s.g.classList.remove('editable-selected');}selectedEditId=null;editDrag=null;$('edit-props').classList.remove('show');editOutline.setAttribute('opacity',0);editHandlesG.setAttribute('opacity',0);}
  drawEditChrome();
}
function hitEditable(target){
  const g=target.closest('.nodeRect,.planet'); if(!g)return null;
  if(g.dataset.id&&EDIT_REG.has(g.dataset.id))return g.dataset.id;
  if(g.dataset.code&&EDIT_REG.has('planet:'+g.dataset.code))return 'planet:'+g.dataset.code;
  return null;
}
function startEditDrag(e,mode,handle){
  const spec=EDIT_REG.get(selectedEditId); if(!spec)return;
  editDrag={mode,handle,start:svgPoint(e.clientX,e.clientY),startBounds:spec.getBounds(),box:boundsToBox(spec.getBounds())};
  e.preventDefault();e.stopPropagation();
  svg.setPointerCapture(e.pointerId);
}
function onEditPointerDown(e){
  if(!editMode)return;
  if(e.target.classList&&e.target.classList.contains('edit-handle')){startEditDrag(e,'resize',e.target.dataset.handle);return;}
  const id=hitEditable(e.target);
  if(id){selectEditable(id);startEditDrag(e,'move');return;}
  if(!e.target.closest('.hud')){editDrag=null;}
}
let editRaf=null,editDragPt=null;
function processEditDrag(){
  editRaf=null;
  if(!editDrag||!selectedEditId||!editDragPt)return;
  const spec=EDIT_REG.get(selectedEditId),pt=editDragPt;
  const dx=pt.x-editDrag.start.x,dy=pt.y-editDrag.start.y;
  let box={...editDrag.box};
  if(editDrag.mode==='move'){
    box.x+=dx;box.y+=dy;
  }else{
    const h=editDrag.handle,min=20;
    if(h.includes('e'))box.w=Math.max(min,editDrag.box.w+dx);
    if(h.includes('s'))box.h=Math.max(min,editDrag.box.h+dy);
    if(h.includes('w')){box.w=Math.max(min,editDrag.box.w-dx);box.x=editDrag.box.x+editDrag.box.w-box.w;}
    if(h.includes('n')){box.h=Math.max(min,editDrag.box.h-dy);box.y=editDrag.box.y+editDrag.box.h-box.h;}
  }
  spec.setBounds(boxToBounds(box,spec));markLayoutDirty();drawEditChrome();refreshAllFlows();
}
function onEditPointerMove(e){
  if(!editDrag||!selectedEditId)return;
  editDragPt=svgPoint(e.clientX,e.clientY);
  if(!editRaf)editRaf=requestAnimationFrame(processEditDrag);
}
function onEditPointerUp(){
  if(editRaf){cancelAnimationFrame(editRaf);editRaf=null;}
  editDragPt=null;
  const wasDirty=layoutDirty;
  if(editDrag){updateEditProps();drawEditChrome();}
  editDrag=null;svg.classList.remove('grabbing');
  if(wasDirty)schedulePersistLayout();
}
['ep-x','ep-y','ep-w','ep-h','ep-r'].forEach(id=>{
  $(id).addEventListener('change',()=>{
    if(!selectedEditId)return;
    const spec=EDIT_REG.get(selectedEditId);
    if(spec.type==='planet')applyBoundsToSelected({cx:$('ep-x').value,cy:$('ep-y').value,r:$('ep-r').value});
    else if(spec.getBounds().x!=null)applyBoundsToSelected({x:+$('ep-x').value-$('ep-w').value/2,y:+$('ep-y').value-$('ep-h').value/2,w:$('ep-w').value,h:$('ep-h').value});
    else applyBoundsToSelected({cx:$('ep-x').value,cy:$('ep-y').value,w:$('ep-w').value,h:$('ep-h').value});
  });
});
$('b-edit').onclick=()=>setEditMode(!editMode);
$('b-save-edit').onclick=()=>saveLayout();
$('b-reset-layout').onclick=()=>resetLayout();
$('b-cancel-edit').onclick=()=>{
  if(savedLayoutSnapshot){applyLayoutElements(JSON.parse(savedLayoutSnapshot).elements);layoutDirty=false;$('edit-dirty').style.display='none';}
  setEditMode(false);
};
svg.addEventListener('pointerdown',onEditPointerDown);
svg.addEventListener('pointermove',onEditPointerMove);
svg.addEventListener('pointerup',onEditPointerUp);
svg.addEventListener('pointercancel',onEditPointerUp);
svg.addEventListener('click',e=>{if(editMode){e.stopPropagation();e.preventDefault();}},true);
window.addEventListener('beforeunload',()=>{if(layoutDirty)persistLayout();});
loadSavedLayout();

/* pan + zoom */
const vp=$('viewport');
const applyView=()=>vp.setAttribute('transform',`translate(${view.x} ${view.y}) scale(${view.k})`);
const fit=()=>{view={x:0,y:0,k:1};applyView();};fit();
let sx,sy,vx,vy;
svg.addEventListener('pointerdown',e=>{if(editMode)return;
  if(e.target.closest('.planet')||e.target.closest('.nodeRect'))return;
  dragging=true;svg.classList.add('grabbing');sx=e.clientX;sy=e.clientY;vx=view.x;vy=view.y;svg.setPointerCapture(e.pointerId);});
svg.addEventListener('pointermove',e=>{if(!dragging)return;view.x=vx+(e.clientX-sx);view.y=vy+(e.clientY-sy);applyView();});
svg.addEventListener('pointerup',()=>{dragging=false;svg.classList.remove('grabbing');});
svg.addEventListener('wheel',e=>{e.preventDefault();const r=svg.getBoundingClientRect();
  const px=(e.clientX-r.left)/r.width*VB[2],py=(e.clientY-r.top)/r.height*VB[3];
  const f=e.deltaY<0?1.12:1/1.12,nk=Math.max(.45,Math.min(3,view.k*f)),wx=(px-view.x)/view.k,wy=(py-view.y)/view.k;
  view.k=nk;view.x=px-wx*nk;view.y=py-wy*nk;applyView();},{passive:false});
$('b-in').onclick=()=>{view.k=Math.min(3,view.k*1.18);applyView();};
$('b-out').onclick=()=>{view.k=Math.max(.45,view.k/1.18);applyView();};
$('b-fit').onclick=fit;
$('b-all').onclick=()=>openAllApis();
$('b-orbit').onclick=e=>{orbitOn=!orbitOn;e.target.classList.toggle('active',orbitOn);e.target.textContent=(orbitOn?'⏸':'▶')+' Orbit';};
$('b-flow').onclick=e=>{flowOn=!flowOn;e.target.classList.toggle('active',flowOn);};

$('search').addEventListener('input',e=>{
  const q=e.target.value.trim().toUpperCase();
  if(!q){highlight(selected);return;}
  const monQ=normMonQuery(q);
  if(monQ){
    if(monQ==='M1'){showPanel('MF','Mainframe','info',row('Monitoring','M1')+row('System','MF'));return;}
    const msCell=CFG.ms.find(m=>Array.isArray(m)&&String(m[2]||'').toUpperCase()===monQ);
    if(msCell){const sn=msCell[0],fn=msCell[1];openGroupBox('ms',fn.toUpperCase());return;}
    const flat=allApiItems();
    if(flat.some(it=>matchesMonQuery(monQ,it))){openAllApis(monQ);return;}
    const app=PLANETS.find(p=>String(p.mon||'').toUpperCase()===monQ);
    if(app){selected=app.code;highlight(app.code);openApp(app);return;}
    for(const sid of ['mongo','aims']){
      const spine=(CFG.spine||[]).find(s=>s.id===sid);
      if(spine&&String(spine.mon||'').toUpperCase()===monQ){openGroupBox(sid,monQ);return;}
    }
  }
  const flat=allApiItems();
  if(flat.some(s=>s.name.toUpperCase().includes(q)||(s.address&&s.address.toUpperCase().includes(q))||matchesMonQuery(q,s))){openAllApis(q);return;}
  for(const box of (CFG.groupBoxes||[])){
    const items=groupItems(box.id);
    if((box.monRange&&box.monRange.toUpperCase().includes(q))||items.some(s=>s.name.toUpperCase().includes(q)||(s.address&&s.address.toUpperCase().includes(q))||matchesMonQuery(q,s))){openGroupBox(box.id,q);return;}
  }
  if(groupItems('ms').some(s=>s.name.toUpperCase().includes(q)||matchesMonQuery(q,s))){openGroupBox('ms',q);return;}
  const h=PLANETS.find(p=>p.code.includes(q)||p.name.toUpperCase().includes(q)||String(p.mon||'').toUpperCase().includes(q));
  if(h){selected=h.code;highlight(h.code);}else highlight(null);
});

/* observability */
function toggleFabricObservability(){
  const m=$('metrics');
  if(!m||panelEl.classList.contains('open'))return;
  m.classList.remove('metrics-hidden');
  m.classList.toggle('open');
}
$('metrics-toggle').onclick=e=>{e.stopPropagation();toggleFabricObservability();};
$('legend-toggle').onclick=()=>$('legend-panel').classList.toggle('open');
$('ticker-toggle').onclick=()=>$('ticker').classList.toggle('open');
let tps=420,lat=38,err=.4,lag=120;
const sd=Array.from({length:48},()=>R(.3,.7)),spark=$('spark');
function drawSpark(){spark.innerHTML='';const w=300,h=34,n=sd.length;let d='';
  sd.forEach((v,i)=>{const x=i/(n-1)*w,y=h-v*h;d+=(i?'L':'M')+x.toFixed(1)+' '+y.toFixed(1)+' ';});
  spark.appendChild(el('path',{d:d+`L ${w} ${h} L 0 ${h} Z`,fill:'rgba(89,224,255,.12)'}));
  spark.appendChild(el('path',{d,fill:'none',stroke:'var(--cyan)','stroke-width':1.6}));}
const step=(v,lo,hi,a)=>Math.max(lo,Math.min(hi,v+R(-a,a)));
const initH=countHealth();
$('m-down').textContent=initH.down;
$('m-up').textContent=initH.ok+'/'+initH.total;
$('m-apis').textContent=initH.total;
setInterval(()=>{tps=step(tps,120,920,60);lat=step(lat,9,95,7);err=step(err,0,4.5,.25);lag=step(lag,0,600,45);
  const h=countHealth();
  $('m-tps').textContent=Math.round(tps);$('m-lat').textContent=Math.round(lat);
  $('m-err').textContent=h.down?Math.max(err,h.down*.08).toFixed(2):err.toFixed(2);
  $('m-lag').textContent=Math.round(lag);
  $('m-down').textContent=h.down; $('m-up').textContent=h.ok+'/'+h.total;
  sd.push(tps/950);sd.shift();drawSpark();},1200);
drawSpark();
pollHealth(true);
setInterval(()=>pollHealth(false),45000);
setInterval(()=>{const d=new Date();$('clock').textContent=d.toLocaleTimeString('en-GB',{hour12:false})+' IST';},1000);

const feed=$('feed'),evApps=CFG.apps.map(a=>a[0]),tg=['ODM','OFM','Kafka','Redis','MongoDB','AIMS','SP','ExtAPI','IntAPI','JEPPP','ORI','CMS'],vb=['→','⇄','⟶'];
let evc=0;
function emit(){const a=evApps[Math.floor(R(0,evApps.length))],t=tg[Math.floor(R(0,tg.length))],ms=Math.round(R(3,160)),roll=Math.random();
  const cls=t==='ORI'?'crit':roll>.9?'warn':'ok',msg=cls==='crit'?'TIMEOUT':cls==='warn'?'RETRY':'OK',fl='6E'+Math.floor(R(1000,9999));
  const r=document.createElement('div');r.className='e';
  r.innerHTML=`<span class="t">${new Date().toLocaleTimeString('en-GB',{hour12:false})}</span><span class="id">${fl}</span><span>${a} ${vb[Math.floor(R(0,3))]} ${t}</span><span class="t">${ms}ms</span><span class="${cls}">${msg}</span>`;
  feed.prepend(r);while(feed.childElementCount>9)feed.lastChild.remove();evc++;}
setInterval(emit,850);setInterval(()=>{$('eps').textContent=Math.round(evc/3)+'/s';evc=0;},3000);emit();emit();emit();
</script>
</body>
</html>
"""

def main():
    base = Path(__file__).resolve().parent
    config = build_config(base)
    html = TEMPLATE.replace("__CONFIG__", json.dumps(config))
    out = base / "index.html"
    docs_dir = base / "docs"
    docs_dir.mkdir(exist_ok=True)
    docs_out = docs_dir / "index.html"
    out.write_text(html, encoding="utf-8")
    docs_out.write_text(html, encoding="utf-8")
    (docs_dir / ".nojekyll").touch()
    groups = config.get("apiGroups", {})
    down = [
        it["name"]
        for items in groups.values()
        for it in items
        if it.get("health") in ("down", "crit")
    ]
    counts = {k: len(v) for k, v in groups.items()}
    print(f"[ok] wrote {out}  ({out.stat().st_size/1024:.1f} KB)")
    print(f"[ok] wrote {docs_out}  (GitHub Pages)")
    print(f"[i] apps={len(config['apps'])}  ms={len(config['ms'])}  group-boxes={len(config.get('groupBoxes', []))}")
    print(f"[i] group counts: {counts}")
    print(f"[i] internal panel lists {counts.get('internal', 0)} APIs on click")
    print(f"[i] APIs DOWN (blinking): {down or 'none'}")

if __name__ == "__main__":
    main()
