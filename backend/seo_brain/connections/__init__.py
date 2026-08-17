"""External connection checks (read-only): Google Search Console, GA4, WordPress REST.

Every check returns a `ConnectionResult` and is persisted in `site_connections` so the UI can show the last
known state without re-calling Google. Nothing here writes to any external system.
"""
from .service import ConnectionResult, ConnectionsService

__all__ = ["ConnectionResult", "ConnectionsService"]
