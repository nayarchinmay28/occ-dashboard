#!/usr/bin/env python3
"""Extract OCC Hub API names from draw.io XML into occ_data.json."""

from __future__ import annotations

import html
import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

SOURCE = "OCCHUB_Drawio_File_V1.drawio"
OUT = "occ_data.json"
REPORT = "EXTRACTION_REPORT.md"

GROUP_KEYS = [
    "internal",
    "external",
    "jobs",
    "kafka_producer",
    "kafka_consumer",
    "redis",
    "shared_path",
    "sp",
    "ms",
    "mongo",
    "aims",
    "uncategorized",
]

# First match wins (case-insensitive on ancestor chain text).
GROUP_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("internal", ("internal api", "internal", "service mesh", "internal endpoints")),
    ("external", ("external api", "external", "partner", "external services")),
    ("jobs", ("job", "cron", "scheduler", "batch", "cron job")),
    ("kafka_producer", ("kafka prod", "kafka producer", "producer topic")),
    ("kafka_consumer", ("kafka cons", "kafka consumer", "consumer topic")),
    ("redis", ("redis", "cache")),
    ("shared_path", ("shared path", "shared")),
    ("sp", ("stored procedure", "sproc", " sp", "[cra].", "[dbo].")),
    ("mongo", ("mongo", "mongodb")),
    ("aims", ("aims",)),
    ("apps", ("app", "screen", "module")),
]

MS_NAME = re.compile(r"^occhub-.+-ms$", re.I)

RED_STYLE = ("#f8cecc", "#b85450", "fillcolor=#e51400", "fillcolor=red", "strokecolor=#b85450")
AMBER_STYLE = ("#fff2cc", "#d6b656", "230, 81, 0", "#e65100")
BROKER_RE = re.compile(
    r"amq-streams-prod-kafka-bootstrap[^\s<]+", re.I
)
DOWN_TEXT = re.compile(r"\b(down|inactive)\b", re.I)
STRUCTURAL = re.compile(
    r"^(M\d+|\(M[\d,\s\-]+\)|\d+|ooo|end points and monitoring points show separately)$",
    re.I,
)
FRAME_LABELS = {
    "external services",
    "cron job",
    "shared path",
    "kafka consumer",
    "kafka producer",
    "internal endpoints",
    "micro services",
    "sp",
}
KAFKA_TOPIC = re.compile(r"[\w.-]+\.json", re.I)
APP_ACRONYM = re.compile(r"\(([A-Z0-9]{2,6})\)\s*$")


def clean_value(raw: str | None) -> str:
    if not raw:
        return ""
    text = html.unescape(raw)
    text = re.sub(r"<br\s*/?>", " ", text, flags=re.I)
    text = re.sub(r"<[^>]+>", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def geom(cell: ET.Element) -> tuple[float, float, float, float] | None:
    g = cell.find("mxGeometry")
    if g is None:
        return None
    return (
        float(g.get("x", 0)),
        float(g.get("y", 0)),
        float(g.get("width", 0)),
        float(g.get("height", 0)),
    )


def centroid(cell: ET.Element) -> tuple[float, float] | None:
    g = geom(cell)
    if not g:
        return None
    x, y, w, h = g
    return x + w / 2, y + h / 2


def inside(cx: float, cy: float, box: tuple[float, float, float, float]) -> bool:
    fx, fy, fw, fh = box
    return fx <= cx <= fx + fw and fy <= cy <= fy + fh


def health_from_style(style: str) -> str | None:
    sl = style.lower()
    if any(tok in sl for tok in RED_STYLE):
        return "down"
    if any(tok in sl for tok in AMBER_STYLE):
        return "warn"
    return None


def health_from_text(text: str, style: str) -> str:
    h = health_from_style(style)
    if h:
        return h
    if DOWN_TEXT.search(text):
        return "down"
    return "ok"


def health_from_html_topic(raw: str, topic: str) -> str:
    for m in re.finditer(r"<span[^>]*>([^<]+\.json)</span>", raw, re.I):
        if m.group(1).strip() != topic:
            continue
        tag_start = raw.rfind("<span", 0, m.start())
        tag = raw[tag_start : m.end()].lower()
        if any(tok in tag for tok in RED_STYLE):
            return "down"
        if any(tok in tag for tok in AMBER_STYLE):
            return "warn"
    if ".error." in topic.lower():
        return "warn"
    return "ok"


def kafka_broker(chain: list[str]) -> str:
    for part in chain:
        m = BROKER_RE.search(part)
        if m:
            return m.group(0)
    return ""


def parse_job(raw: str) -> tuple[str, str]:
    sched_m = re.search(r"\(([^()]*(?:daily|min|hrs|AM|PM)[^()]*)\)\s*$", raw, re.I)
    schedule = sched_m.group(1).strip() if sched_m else ""
    endpoint = raw
    if schedule:
        endpoint = raw[: sched_m.start()].strip()
    endpoint = endpoint.strip("()").strip()
    return endpoint, schedule


def make_item(
    name: str,
    health: str,
    source: str,
    address: str = "",
    method: str = "",
) -> dict:
    item = {"name": name, "health": health, "source": source}
    if address:
        item["address"] = address
    if method:
        item["method"] = method
    return item


def is_structural(name: str) -> bool:
    if not name:
        return True
    low = name.lower().strip()
    if low in FRAME_LABELS:
        return True
    if STRUCTURAL.match(name):
        return True
    if re.match(r"^\(M[\d,\s\-]+\)$", name, re.I):
        return True
    if name.startswith("(M") and ")" in name:
        return True
    if "kafka topic" in low and "amq-streams" in low:
        return True
    if low.endswith("topic's") or low.endswith("topics"):
        return True
    return False


def kafka_group_from_chain(chain: str) -> str | None:
    low = chain.lower()
    if "kafka producer" in low or "streamorchestrator" in low and "topic" in low:
        return "kafka_producer"
    if "kafka consumer" in low or "kafka topic" in low:
        return "kafka_consumer"
    if "joc kafka" in low or "aims kafka" in low:
        return "kafka_consumer"
    return None


def classify_group(chain: str, name: str, spatial_frame: str | None) -> str:
    low_name = name.lower()
    if MS_NAME.match(name) or (low_name.startswith("occhub-") and low_name.endswith("-ms")):
        return "ms"
    if KAFKA_TOPIC.fullmatch(name):
        kg = kafka_group_from_chain(chain)
        if kg:
            return kg
    hay = " / ".join(filter(None, [chain, spatial_frame or "", name])).lower()
    kg = kafka_group_from_chain(hay)
    if kg:
        return kg
    for group, needles in GROUP_RULES:
        if group in ("mongo", "aims", "apps"):
            continue
        if any(n in hay for n in needles):
            return group
    if spatial_frame:
        frame_map = {
            "External Services": "external",
            "Cron Job": "jobs",
            "Internal endpoints": "internal",
            "Kafka Consumer": "kafka_consumer",
            "Kafka Producer": "kafka_producer",
            "Shared Path": "shared_path",
        }
        if spatial_frame in frame_map:
            return frame_map[spatial_frame]
        if spatial_frame == "Micro services" and (
            MS_NAME.match(name) or name.lower() == "occhub-mf"
        ):
            return "ms"
    if low_name.startswith("/") or "/api/" in low_name or low_name.startswith("api/"):
        return "internal"
    if "[cra]." in low_name or "[dbo]." in low_name or "_sp_" in low_name:
        return "sp"
    if low_name == "occhub-mf":
        return "ms"
    return "uncategorized"


def app_code(name: str) -> str:
    m = APP_ACRONYM.search(name)
    if m:
        return m.group(1)
    words = [w for w in re.split(r"[^A-Za-z0-9]+", name) if w and w.lower() not in {"and", "the", "of"}]
    if len(words) >= 2:
        return "".join(w[0] for w in words[:4]).upper()[:6]
    return (words[0][:6] if words else name[:6]).upper()


def sort_health(items: list[dict]) -> list[dict]:
    pri = {"down": 0, "warn": 1, "ok": 2}

    def key(it: dict) -> tuple[int, int]:
        return pri.get(it.get("health", "ok"), 2), 0

    indexed = list(enumerate(items))
    indexed.sort(key=lambda t: (pri.get(t[1].get("health", "ok"), 2), t[0]))
    return [it for _, it in indexed]


class Extractor:
    def __init__(self, path: Path):
        self.path = path
        self.root = ET.parse(path).getroot()
        self.cells: dict[str, ET.Element] = {
            c.get("id"): c for c in self.root.iter("mxCell") if c.get("id")
        }
        self.page = ""
        for d in self.root.findall("diagram"):
            self.page = d.get("name", "").strip()
        self.frames: list[tuple[str, str, tuple[float, float, float, float], float]] = []
        for c in self.root.iter("mxCell"):
            if "umlFrame" not in c.get("style", ""):
                continue
            g = geom(c)
            if not g:
                continue
            name = clean_value(c.get("value"))
            area = g[2] * g[3]
            self.frames.append((name, c.get("id", ""), g, area))
        self.frames.sort(key=lambda x: x[3])

        self.leaf_cells_seen = 0
        self.skipped: list[dict] = []
        self.seen: set[tuple[str, str]] = set()
        self.groups: dict[str, list[dict]] = {k: [] for k in GROUP_KEYS}
        self.microservices: list[str] = []
        self.apps: list[dict] = []
        self.frame_counts: dict[str, int] = {}

    def spatial_frame(self, cell: ET.Element) -> str | None:
        c = centroid(cell)
        if not c:
            return None
        cx, cy = c
        for name, _fid, box, _area in self.frames:
            if name.lower() == "ooo":
                continue
            if inside(cx, cy, box):
                return name
        return None

    def ancestor_chain(self, cell_id: str) -> list[str]:
        chain: list[str] = []
        cur = cell_id
        while cur and cur in self.cells:
            parent_id = self.cells[cur].get("parent")
            if not parent_id or parent_id not in self.cells:
                break
            parent = self.cells[parent_id]
            val = clean_value(parent.get("value"))
            if val:
                chain.append(val)
            cur = parent_id
        chain.reverse()
        if self.page:
            chain = [self.page] + chain
        return chain

    def add_item(
        self,
        name: str,
        group: str,
        source: str,
        health: str,
        cell_id: str,
        reason_skip: str | None = None,
        address: str = "",
        method: str = "",
    ) -> None:
        if reason_skip:
            self.skipped.append({"cell_id": cell_id, "raw": name, "reason": reason_skip})
            return
        if is_structural(name):
            self.skipped.append({"cell_id": cell_id, "raw": name, "reason": "structural label"})
            return
        if group == "ms":
            if name == "occhub-mf":
                self.skipped.append(
                    {"cell_id": cell_id, "raw": name, "reason": "mainframe box (M1), not MS grid"}
                )
                return
            if name not in self.microservices:
                self.microservices.append(name)
            group = "ms"
        if group == "apps":
            code = app_code(name)
            if not any(a["code"] == code for a in self.apps):
                ring = len(self.apps) % 2
                app_item = {
                    "code": code,
                    "name": name,
                    "ring": ring,
                    "health": health,
                    "source": source,
                }
                if address:
                    app_item["address"] = address
                self.apps.append(app_item)
            return
        if group not in self.groups:
            group = "uncategorized"
        key = (name, group, address) if group == "internal" else (name, group)
        if key in self.seen:
            return
        self.seen.add(key)
        item = make_item(name, health, source, address=address, method=method)
        if group == "internal" and address:
            mon_m = re.match(r"^(M\d+)", address, re.I)
            if mon_m:
                item["mon"] = mon_m.group(1).upper()
        self.groups[group].append(item)

    def extract_table_internal(self, cell: ET.Element) -> None:
        raw = cell.get("value", "")
        tds = [
            clean_value(m.group(1))
            for m in re.finditer(r"<td[^>]*>(.*?)</td>", raw, re.I | re.S)
        ]
        rows = [tds[i : i + 3] for i in range(0, len(tds) - len(tds) % 3, 3)]
        self.leaf_cells_seen += len(rows)
        chain = " / ".join(self.ancestor_chain(cell.get("id", "")))
        for row in rows:
            if len(row) < 3:
                self.skipped.append(
                    {
                        "cell_id": cell.get("id"),
                        "raw": str(row),
                        "reason": "incomplete internal table row",
                    }
                )
                continue
            mnum, method, path = row[0], row[1], row[2]
            if not path:
                continue
            source = f"Internal endpoints / {mnum} {method}"
            health = health_from_text(path, cell.get("style", ""))
            self.add_item(
                path,
                "internal",
                source,
                health,
                cell.get("id", ""),
                address=f"{mnum} · {method}",
                method=method,
            )

    def extract_table_sp(self, cell: ET.Element) -> None:
        raw = cell.get("value", "")
        rows_html = re.findall(r"<tr[^>]*>(.*?)</tr>", raw, re.I | re.S)
        self.leaf_cells_seen += len(rows_html)
        for row_html in rows_html:
            tds = [
                clean_value(m.group(1))
                for m in re.finditer(r"<td[^>]*>(.*?)</td>", row_html, re.I | re.S)
            ]
            text = " ".join(t for t in tds if t)
            if not text:
                continue
            parts = re.split(r"(?=M\d+\s)", text)
            for part in parts:
                part = part.strip()
                if not part:
                    continue
                m = re.match(r"^(M\d+)\s+(.+)$", part, re.I)
                proc = m.group(2).strip() if m else part
                mref = m.group(1) if m else ""
                if re.fullmatch(r"M\d+", proc, re.I) or proc.upper() == "SP":
                    continue
                source = "SP / " + " / ".join(self.ancestor_chain(cell.get("id", "")))
                health = health_from_text(proc, cell.get("style", ""))
                item = make_item(
                    proc,
                    health,
                    source,
                    address=mref or "stored procedure",
                )
                if mref:
                    item["mon"] = mref.upper()
                key = (proc, "sp")
                if key in self.seen:
                    continue
                self.seen.add(key)
                self.groups["sp"].append(item)

    def extract_kafka_topics(self, cell: ET.Element, spatial: str | None) -> None:
        raw = cell.get("value", "")
        topics = KAFKA_TOPIC.findall(raw)
        if not topics:
            return
        self.leaf_cells_seen += len(topics)
        chain = " / ".join(self.ancestor_chain(cell.get("id", "")))
        group = kafka_group_from_chain(chain)
        if not group:
            group = classify_group(chain, topics[0], spatial)
        if group not in ("kafka_consumer", "kafka_producer"):
            group = "uncategorized"
        broker = kafka_broker(self.ancestor_chain(cell.get("id", "")))
        for topic in topics:
            source = " / ".join(filter(None, [chain, spatial, topic]))
            health = health_from_html_topic(raw, topic)
            if health == "ok":
                health = health_from_text(topic, cell.get("style", ""))
            self.add_item(
                topic,
                group,
                source,
                health,
                cell.get("id", ""),
                address=broker or "kafka topic",
            )

    def extract_cell(self, cell: ET.Element) -> None:
        if cell.get("vertex") != "1":
            return
        raw = cell.get("value")
        if not raw:
            return
        cid = cell.get("id", "")
        style = cell.get("style", "")

        if "<td" in raw and cid == "nB40ue4nVSqGBbk0N7Ms-1":
            self.extract_table_internal(cell)
            return
        if "<td" in raw and cid == "uiy4wioe-8W6FQFdPiAP-9":
            self.extract_table_sp(cell)
            return
        if KAFKA_TOPIC.search(raw):
            spatial = self.spatial_frame(cell)
            self.extract_kafka_topics(cell, spatial)
            return

        name = clean_value(raw)
        if not name:
            self.skipped.append({"cell_id": cid, "raw": raw[:80], "reason": "empty after clean"})
            return

        self.leaf_cells_seen += 1
        spatial = self.spatial_frame(cell)
        if spatial:
            self.frame_counts[spatial] = self.frame_counts.get(spatial, 0) + 1
        chain = " / ".join(self.ancestor_chain(cid))

        # Apps: rounded boxes outside inner frames (or anywhere with rounded style + div app name)
        if "rounded=1" in style and spatial is None and not name.startswith(("api", "/")):
            if not is_structural(name) and len(name) > 3:
                source = " / ".join(filter(None, [self.page, "Apps"]))
                health = health_from_text(name, style)
                self.add_item(
                    name,
                    "apps",
                    source,
                    health,
                    cid,
                    address="Operations application",
                )
                return

        if is_structural(name):
            self.skipped.append({"cell_id": cid, "raw": name, "reason": "structural label"})
            return

        if "shape=cylinder" in style:
            low = name.lower()
            if "mongo" in low:
                grp, addr = "mongo", "document store · Occhub"
            elif "aims" in low:
                grp, addr = "aims", "system of record · MSQL"
            else:
                self.skipped.append(
                    {"cell_id": cid, "raw": name, "reason": "data-store node (not API leaf)"}
                )
                return
            source = " / ".join(filter(None, [chain, spatial]))
            health = health_from_text(name, style)
            self.add_item(name, grp, source, health, cid, address=addr)
            return

        if name.lower() == "redis":
            source = " / ".join(filter(None, [chain, spatial]))
            health = health_from_text(name, style)
            self.add_item(
                name,
                "redis",
                source,
                health,
                cid,
                address="OCP cache layer",
            )
            return

        group = classify_group(chain, name, spatial)
        source = " / ".join(filter(None, [chain, spatial]))
        health = health_from_text(name, style)

        address = ""
        method = ""
        item_name = name
        if group == "jobs":
            item_name, address = parse_job(name)
            address = address or "scheduled job"
        elif group == "external":
            address = spatial or "External Services"
        elif group == "ms":
            address = "Micro services · OpenShift"
        elif group == "shared_path":
            address = spatial or "Shared Path"
        elif MS_NAME.match(name):
            address = "Micro services · OpenShift"
            group = "ms"

        self.add_item(
            item_name,
            group,
            source,
            health,
            cid,
            address=address,
            method=method,
        )

    def run(self) -> dict:
        for cell in self.root.iter("mxCell"):
            self.extract_cell(cell)

        for key in self.groups:
            self.groups[key] = sort_health(self.groups[key])

        names_in_groups = sum(len(v) for v in self.groups.values())
        names_extracted = names_in_groups + len(self.apps)

        totals = {
            "internal": len(self.groups["internal"]),
            "external": len(self.groups["external"]),
            "jobs": len(self.groups["jobs"]),
            "apps": len(self.apps),
            "uncategorized": len(self.groups["uncategorized"]),
        }

        return {
            "meta": {
                "source_file": self.path.name,
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "leaf_cells_seen": self.leaf_cells_seen,
                "names_extracted": names_extracted,
                "totals": totals,
                "skipped": self.skipped,
                "frame_counts": self.frame_counts,
            },
            "groups": self.groups,
            "microservices": self.microservices,
            "apps": self.apps,
        }


def write_report(data: dict, path: Path) -> None:
    meta = data["meta"]
    groups = data["groups"]
    lines = [
        "# OCC Hub Extraction Report",
        "",
        f"**Source:** `{meta['source_file']}`  ",
        f"**Generated:** {meta['generated_at']}  ",
        "",
        "## Per-group counts",
        "",
        "| Group | Count |",
        "|-------|------:|",
    ]
    for g in GROUP_KEYS:
        lines.append(f"| {g} | {len(groups[g])} |")
    lines.append(f"| apps (floating) | {len(data['apps'])} |")
    lines.append(f"| microservices | {len(data['microservices'])} |")
    lines.append("")
    lines.append("## Health summary")
    lines.append("")
    lines.append("| Group | ok | warn | down |")
    lines.append("|-------|---:|-----:|-----:|")
    for g in GROUP_KEYS:
        items = groups[g]
        if not items:
            continue
        ok = sum(1 for i in items if i.get("health") == "ok")
        warn = sum(1 for i in items if i.get("health") == "warn")
        down = sum(1 for i in items if i.get("health") in ("down", "crit"))
        lines.append(f"| {g} | {ok} | {warn} | {down} |")
    lines.append("")
    lines.append(f"**leaf_cells_seen:** {meta['leaf_cells_seen']}  ")
    lines.append(f"**names_extracted:** {meta['names_extracted']}  ")
    lines.append(
        f"**sum(groups)+apps:** {sum(len(groups[g]) for g in GROUP_KEYS) + len(data['apps'])}  "
    )
    lines.append(f"**skipped cells:** {len(meta['skipped'])}  ")
    lines.append("")
    lines.append("## Spatial frame → group mapping")
    lines.append("")
    lines.append("| Frame (draw.io umlFrame) | Items spatially inside | Primary group |")
    lines.append("|--------------------------|------------------------:|---------------|")
    frame_map = {
        "External Services": "external",
        "Cron Job": "jobs",
        "Internal endpoints": "internal",
        "Kafka Consumer": "kafka_consumer",
        "Kafka Producer": "kafka_producer",
        "Shared Path": "shared_path",
        "Micro services": "ms → microservices[]",
    }
    for frame, count in sorted(meta.get("frame_counts", {}).items()):
        primary = frame_map.get(frame, "uncategorized")
        lines.append(f"| {frame} | {count} | {primary} |")
    lines.append("")
    lines.append("## microservices")
    lines.append("")
    for ms in data["microservices"]:
        lines.append(f"- {ms}")
    lines.append("")
    lines.append("## uncategorized (full list)")
    lines.append("")
    if groups["uncategorized"]:
        for item in groups["uncategorized"]:
            lines.append(f"- `{item['name']}` — {item['source']}")
    else:
        lines.append("_None_")
    lines.append("")
    if meta["skipped"]:
        lines.append("## Skipped cells (sample)")
        lines.append("")
        for s in meta["skipped"][:40]:
            lines.append(f"- `{s['cell_id']}`: {s['reason']} — `{s['raw'][:80]}`")
        if len(meta["skipped"]) > 40:
            lines.append(f"- … and {len(meta['skipped']) - 40} more")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    base = Path(__file__).resolve().parent
    src = base / SOURCE
    if not src.exists():
        raise SystemExit(f"Source not found: {src}")

    data = Extractor(src).run()
    out = base / OUT
    out.write_text(json.dumps(data, indent=2), encoding="utf-8")
    write_report(data, base / REPORT)

    g = data["groups"]
    print(
        "[ok] wrote",
        out,
        {
            k: len(v)
            for k, v in g.items()
        },
    )
    print(
        "apps",
        len(data["apps"]),
        "microservices",
        len(data["microservices"]),
        "extracted",
        data["meta"]["names_extracted"],
    )


if __name__ == "__main__":
    main()
