#!/bin/bash
# Local OCC Hub — http://localhost:8765
cd "$(dirname "$0")"
PORT="${OCC_PORT:-8765}"
if lsof -ti:"$PORT" >/dev/null 2>&1; then
  echo "[ok] Server already on port $PORT"
else
  echo "[i] Starting occ_server.py on port $PORT ..."
  python3 occ_server.py &
  sleep 1
fi
open "http://localhost:${PORT}/"
