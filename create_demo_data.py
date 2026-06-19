#!/usr/bin/env python3
"""
Build occ_data_demo.json — sample health states for the OCC hub UI.

Most endpoints stay green (ok). A handful are red (down) or amber (warn)
so the map blinks in a few places without flooding the view in yellow.

Usage:
  python3 create_demo_data.py
  OCC_DATA=occ_data_demo.json python3 generate_occ.py
  OCC_DATA=occ_data_demo.json python3 occ_server.py
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

BASE = Path(__file__).resolve().parent
SOURCE = BASE / "occ_data.json"
OUT = BASE / "occ_data_demo.json"

# Red internal APIs — makes the Internal API box blink on the map
INTERNAL_DOWN = [
    "/crew/api/v1/crew-dashboard/open-trips-main",
    "/crew/api/v1/token/get-token",
    "/flight/api/v1/ctot/send-email",
    "/flight/api/v1/ctot/upload",
]

# Other red APIs (different groups)
DOWN_APIS: list[tuple[str | None, str]] = [
    *(( "internal", name) for name in INTERNAL_DOWN),
    ("external", "NavBlue"),
]

# 2 amber APIs — not all kafka topics yellow
WARN_APIS: list[tuple[str | None, str]] = [
    ("kafka_producer", "prod.crd.logistics-summary.v1.error.json"),
    ("kafka_consumer", "flight.cancel.event.json"),
]

# 2 red floating apps
DOWN_APPS = {"CRD", "SFM"}


def set_health(groups: dict, group: str | None, name: str, health: str) -> bool:
    items = groups.get(group, []) if group else []
    if group is None:
        for gid, gitems in groups.items():
            for item in gitems:
                if item.get("name") == name:
                    item["health"] = health
                    return True
        return False
    for item in items:
        if item.get("name") == name:
            item["health"] = health
            return True
    return False


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"Missing {SOURCE} — run extract_occ.py first")

    data = json.loads(SOURCE.read_text(encoding="utf-8"))
    groups = data.get("groups", {})

    for items in groups.values():
        for item in items:
            item["health"] = "ok"
    for app in data.get("apps", []):
        app["health"] = "ok"

    missing: list[str] = []
    for group, name in DOWN_APIS:
        if not set_health(groups, group, name, "down"):
            missing.append(f"down {group or '*'}:{name}")
    for group, name in WARN_APIS:
        if not set_health(groups, group, name, "warn"):
            missing.append(f"warn {group or '*'}:{name}")
    for app in data.get("apps", []):
        if app.get("code") in DOWN_APPS:
            app["health"] = "down"

    meta = data.setdefault("meta", {})
    meta["demo"] = True
    meta["demo_note"] = f"Sample health: {len(INTERNAL_DOWN)} down internal APIs, 2 warn APIs, 2 down apps; rest ok"
    meta["demo_generated_at"] = datetime.now(timezone.utc).isoformat()
    if missing:
        meta["demo_missing"] = missing

    OUT.write_text(json.dumps(data, indent=2), encoding="utf-8")
    print(f"[ok] wrote {OUT}  ({OUT.stat().st_size / 1024:.1f} KB)")
    print("[i] down internal:", INTERNAL_DOWN)
    print("[i] warn APIs:", [n for _, n in WARN_APIS])
    print("[i] down apps:", sorted(DOWN_APPS))
    if missing:
        print("[warn] could not find:", missing)
    print("\nRun with demo data:")
    print("  OCC_DATA=occ_data_demo.json python3 generate_occ.py")
    print("  OCC_DATA=occ_data_demo.json python3 occ_server.py")


if __name__ == "__main__":
    main()
