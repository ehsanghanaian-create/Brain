"""Live one-way sync of ads_click_events from the production server into the local ads DB.

READ-ONLY on the server (ssh + sqlite mode=ro); appends only NEW rows (id > local max) locally, so the
local /ads-data dashboard becomes near-live (its own 5s polling picks the rows up). Ctrl+C to stop.

Usage:  python backend/cli/ads-live-sync.py [interval_seconds=12]
"""
from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "data" / "ads-events.db"
SSH = ["ssh", "-i", "C:/Users/Lenovo/.ssh/gearboxemdad_parspack_ed25519", "-o", "BatchMode=yes",
       "-o", "ConnectTimeout=15", "root@185.110.190.125", "python3", "-"]

REMOTE = """
import json, sqlite3, sys
last = int(sys.argv[0]) if False else int({last})
c = sqlite3.connect('file:/opt/seo-brain/runtime-db/ads-events.db?mode=ro', uri=True)
c.row_factory = sqlite3.Row
rows = [dict(r) for r in c.execute('SELECT * FROM ads_click_events WHERE id > ? ORDER BY id LIMIT 800', (last,))]
print(json.dumps(rows, ensure_ascii=False))
"""


def pull_once() -> int:
    with sqlite3.connect(DB, timeout=30) as local:
        last = local.execute("SELECT COALESCE(MAX(id), 0) FROM ads_click_events").fetchone()[0]
    out = subprocess.run(SSH, input=REMOTE.format(last=last), capture_output=True, text=True, timeout=90, encoding="utf-8")
    if out.returncode != 0:
        raise RuntimeError((out.stderr or "ssh failed")[:200])
    rows = json.loads(out.stdout or "[]")
    if not rows:
        return 0
    cols = list(rows[0].keys())
    sql = f"INSERT OR IGNORE INTO ads_click_events({', '.join(cols)}) VALUES({', '.join('?' * len(cols))})"
    with sqlite3.connect(DB, timeout=30) as local:
        local.executemany(sql, [[r.get(c) for c in cols] for r in rows])
    return len(rows)


def main() -> None:
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 12
    print(f"ads live-sync: {DB.name} <- production, every {interval}s (Ctrl+C to stop)")
    while True:
        try:
            n = pull_once()
            if n:
                print(f"[{time.strftime('%H:%M:%S')}] +{n} new events")
        except Exception as e:  # noqa: BLE001 — keep syncing through transient ssh/db hiccups
            print(f"[{time.strftime('%H:%M:%S')}] sync error: {e}")
        time.sleep(interval)


if __name__ == "__main__":
    main()
