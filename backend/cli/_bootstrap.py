"""Shared bootstrap for CLI scripts: repo root + backend package on sys.path."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]          # repository root (data/, config/, .env live here)
BACKEND = Path(__file__).resolve().parents[1]       # backend/ (contains the seo_brain package)
for p in (str(BACKEND), str(ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)
