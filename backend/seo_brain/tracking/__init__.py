"""Traffic Intel — first-party visit tracking for the managed sites (migration 0018).

Why in-house instead of Umami/Plausible/Matomo: 13 sites share one WordPress theme, so there is a single
deployment point; the conversion that matters is a tel: click, which no packaged tool reports out of the box;
a first-party endpoint is not cut off by ad blockers; and Search Console data is already in this database,
so the value is in joining the two, not in collecting page views a second time.
"""
from .channels import classify, device_of, is_bot
from .repository import TrackingRepository
from .service import TrackingService, normalize_path, path_of

__all__ = ["TrackingRepository", "TrackingService", "classify", "device_of", "is_bot", "normalize_path", "path_of"]
