#!/usr/bin/env python3
"""
OCC Hub — static file server + live API health probes for all groups.

Run:
  python3 occ_server.py
  OCC_API_BASE=https://your-gateway.example.com python3 occ_server.py

Open http://localhost:8765
"""

from __future__ import annotations

import json
import os
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse

BASE = Path(__file__).resolve().parent
DATA_PATH = BASE / os.environ.get("OCC_DATA", "occ_data.json")
LAYOUT_PATH = BASE / "occ_layout.json"
PORT = int(os.environ.get("OCC_PORT", "8765"))
API_BASE = os.environ.get("OCC_API_BASE", "").rstrip("/")
PROBE_TIMEOUT = float(os.environ.get("OCC_PROBE_TIMEOUT", "4"))
MAX_WORKERS = int(os.environ.get("OCC_PROBE_WORKERS", "24"))
CACHE_TTL = float(os.environ.get("OCC_CACHE_TTL", "45"))

_cache_lock = threading.Lock()
_cache: dict | None = None
_cache_at = 0.0
_broker_reach: dict[str, bool | None] = {}

HTTP_UP = {200, 201, 202, 204, 301, 302, 307, 308, 400, 401, 403, 404, 405, 409, 422}


def broker_reachable(host: str) -> bool | None:
    """True if broker TCP OK, False if unreachable, None if not checked yet."""
    if host in _broker_reach:
        return _broker_reach[host]
    ok, _ = tcp_reachable(host, 443)
    _broker_reach[host] = ok
    return ok


def kafka_health(name: str, baseline: str, broker_ok: bool | None) -> str:
    """Topic health: use live broker only when reachable; else diagram baseline."""
    if broker_ok is False:
        return baseline
    if ".error." in name.lower():
        return "warn" if baseline == "warn" else "warn"
    return "ok" if broker_ok else baseline


def load_data() -> dict:
    return json.loads(DATA_PATH.read_text(encoding="utf-8"))


def tcp_reachable(host: str, port: int, timeout: float = PROBE_TIMEOUT) -> tuple[bool, str]:
    try:
        ctx = ssl.create_default_context()
        with socket.create_connection((host, port), timeout=timeout) as raw:
            if port == 443:
                with ctx.wrap_socket(raw, server_hostname=host):
                    pass
        return True, f"TCP {host}:{port} OK"
    except Exception as exc:
        return False, str(exc)[:120]


def probe_http(url: str, method: str = "GET") -> tuple[str, int | None, str]:
    """Return (health, status_code, detail)."""
    req_method = "HEAD" if method in ("GET", "HEAD") else method
    req = urllib.request.Request(url, method=req_method)
    req.add_header("User-Agent", "OCC-Hub-Health/1.0")
    try:
        with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as resp:
            code = resp.status
            health = "ok" if code in HTTP_UP else ("warn" if code < 500 else "down")
            return health, code, f"HTTP {code}"
    except urllib.error.HTTPError as exc:
        code = exc.code
        health = "ok" if code in HTTP_UP else ("warn" if code < 500 else "down")
        return health, code, f"HTTP {code}"
    except Exception as exc:
        return "down", None, str(exc)[:120]


def probe_item(group: str, item: dict) -> dict:
    name = item["name"]
    method = item.get("method", "GET")
    baseline = item.get("health", "ok")
    address = item.get("address", "")
    out = {
        "name": name,
        "health": baseline,
        "baseline": baseline,
        "latency_ms": None,
        "detail": "draw.io baseline",
        "group": group,
    }

    # Internal REST paths — probe when gateway base is configured
    if group == "internal" and name.startswith("/") and API_BASE:
        url = API_BASE + name.split("{")[0].rstrip("/")
        if "{" in name:
            url = API_BASE + name.split("{")[0]
        t0 = time.perf_counter()
        health, code, detail = probe_http(url, method)
        out["health"] = health
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        out["detail"] = detail
        out["url"] = url
        return out

    # Kafka consumer/producer — TCP check on bootstrap broker
    if group in ("kafka_consumer", "kafka_producer") and address:
        host = address
        port = 443
        if "://" in address:
            parsed = urlparse(address if "://" in address else f"https://{address}")
            host = parsed.hostname or address
            port = parsed.port or 443
        elif ":" in address and not address.endswith(".json"):
            host, _, port_s = address.partition(":")
            port = int(port_s) if port_s.isdigit() else 443
        elif address == "kafka topic":
            out["detail"] = "topic registry · diagram"
            out["health"] = "warn" if ".error." in name.lower() and baseline == "warn" else baseline
            return out
        else:
            host = address.split(":")[0] if ":" in address else address
            if host.startswith("amq-streams"):
                reach = broker_reachable(host)
                if reach is False:
                    out["detail"] = f"broker unreachable · diagram ({baseline})"
                    out["health"] = kafka_health(name, baseline, False)
                    return out
                t0 = time.perf_counter()
                out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
                out["detail"] = f"broker {host} reachable"
                out["health"] = kafka_health(name, baseline, True)
                return out

        if host and not host.endswith(".json"):
            if host.startswith("amq-streams"):
                reach = broker_reachable(host)
                if reach is False:
                    out["detail"] = f"broker unreachable · diagram ({baseline})"
                    out["health"] = kafka_health(name, baseline, False)
                    return out
                t0 = time.perf_counter()
                out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
                out["detail"] = f"broker {host} reachable"
                out["health"] = kafka_health(name, baseline, True)
                return out
            t0 = time.perf_counter()
            ok, detail = tcp_reachable(host, port)
            out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
            out["detail"] = detail
            out["health"] = "ok" if ok else baseline
            if ok and ".error." in name.lower():
                out["health"] = "warn"
            return out

    # Microservices — optional route probe
    if group == "ms" and API_BASE:
        slug = name.replace("occhub-", "").replace("-ms", "")
        url = f"{API_BASE}/{slug}/actuator/health"
        t0 = time.perf_counter()
        health, _, detail = probe_http(url)
        out["health"] = health
        out["latency_ms"] = round((time.perf_counter() - t0) * 1000)
        out["detail"] = detail
        return out

    # Jobs, SP, external, redis, shared_path, mongo, aims — baseline from diagram
    if baseline in ("down", "crit", "warn"):
        out["health"] = baseline
    return out


def build_health_report(force: bool = False) -> dict:
    global _cache, _cache_at, _broker_reach
    now = time.time()
    with _cache_lock:
        if not force and _cache and (now - _cache_at) < CACHE_TTL:
            return _cache
    if force:
        _broker_reach.clear()

    data = load_data()
    groups = data.get("groups", {})
    tasks: list[tuple[str, dict]] = []
    for gid, items in groups.items():
        for item in items:
            tasks.append((gid, item))

    results: dict[str, list[dict]] = {gid: [] for gid in groups}
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        futures = {pool.submit(probe_item, gid, item): (gid, item) for gid, item in tasks}
        for fut in as_completed(futures):
            gid, item = futures[fut]
            try:
                results[gid].append(fut.result())
            except Exception as exc:
                results[gid].append(
                    {
                        "name": item["name"],
                        "health": "down",
                        "detail": str(exc)[:120],
                        "group": gid,
                    }
                )

    for gid in results:
        results[gid].sort(key=lambda x: x["name"])

    flat = [it for items in results.values() for it in items]
    stats = {
        "total": len(flat),
        "ok": sum(1 for i in flat if i["health"] == "ok"),
        "warn": sum(1 for i in flat if i["health"] == "warn"),
        "down": sum(1 for i in flat if i["health"] in ("down", "crit")),
        "internal": len(groups.get("internal", [])),
    }

    report = {
        "updated": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "api_base": API_BASE or None,
        "stats": stats,
        "groups": results,
    }
    with _cache_lock:
        _cache = report
        _cache_at = now
    return report


def load_layout() -> dict:
    if LAYOUT_PATH.exists():
        return json.loads(LAYOUT_PATH.read_text(encoding="utf-8"))
    return {}


def save_layout(data: dict) -> None:
    LAYOUT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(BASE), **kwargs)

    def log_message(self, fmt, *args):
        if args and str(args[0]).startswith("GET /api/"):
            super().log_message(fmt, *args)

    def end_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def do_GET(self):
        if self.path == "/api/health" or self.path.startswith("/api/health?"):
            force = "force=1" in self.path
            report = build_health_report(force=force)
            body = json.dumps(report).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/api/layout":
            body = json.dumps(load_layout()).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        if self.path == "/":
            self.path = "/index.html"
        return super().do_GET()

    def do_POST(self):
        if self.path == "/api/layout":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
            except json.JSONDecodeError:
                self.send_response(400)
                self.end_headers()
                return
            save_layout(data)
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            body = json.dumps({"ok": True, "saved": str(LAYOUT_PATH)}).encode()
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()


def main():
    if not DATA_PATH.exists():
        raise SystemExit(f"Missing {DATA_PATH} — run extract_occ.py first")
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[ok] OCC Hub → http://localhost:{PORT}")
    print(f"[i]  APIs in occ_data.json: {sum(len(v) for v in load_data().get('groups', {}).values())}")
    print(f"[i]  internal REST: {len(load_data().get('groups', {}).get('internal', []))}")
    if API_BASE:
        print(f"[i]  probing gateway: {API_BASE}")
    else:
        print("[i]  set OCC_API_BASE to probe live internal REST endpoints")
    print("[i]  kafka brokers probed via TCP; diagram colors used for SP/jobs/external")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[ok] stopped")


if __name__ == "__main__":
    main()
