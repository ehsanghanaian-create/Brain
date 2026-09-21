"""A sync must release its SQLite writer before progress callbacks and network I/O."""
import sqlite3

from sqlalchemy import create_engine, text

from seo_brain.common.config import SiteConfig
from seo_brain.database.db import init_db
from seo_brain.wordpress.sync import sync_wordpress


def test_taxonomy_progress_and_network_allow_independent_writer(tmp_path, monkeypatch):
    path = tmp_path / "sync.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    init_db(conn)
    conn.execute("CREATE TABLE writer_probes (phase TEXT NOT NULL)")
    conn.commit()
    engine = create_engine("sqlite:///" + path.as_posix(), connect_args={"timeout": 0.05})
    failures, progress_steps, network_steps = [], [], []

    def write_probe(phase):
        # Same separate-connection pattern used by persisted pipeline progress.
        try:
            with engine.begin() as second:
                second.exec_driver_sql("PRAGMA busy_timeout=50")
                second.execute(text("INSERT INTO writer_probes(phase) VALUES (:phase)"), {"phase": phase})
        except Exception as exc:
            failures.append((phase, str(exc)))

    def progress(step, info):
        progress_steps.append((step, info))
        write_probe("progress:" + step)

    class WordPress:
        authenticated = False

        def __init__(self, *args, **kwargs):
            pass

        def root(self):
            return {"name": "Demo", "url": "https://demo.example"}

        def content_taxonomies(self):
            return {
                "category": {"name": "Categories", "rest_base": "categories", "hierarchical": True, "types": ["post"]},
                "post_tag": {"name": "Tags", "rest_base": "tags", "hierarchical": False, "types": ["post"]},
            }

        def public_content_types(self):
            return {"post": {"rest_base": "posts"}}

        def fetch_all(self, rest_base, params=None):
            network_steps.append(rest_base)
            write_probe("network:" + rest_base)
            if rest_base in ("categories", "tags"):
                return [{"id": 1, "name": "Demo", "slug": "demo", "link": "https://demo.example/" + rest_base + "/demo/", "count": 1}]
            if rest_base == "posts":
                return [{"id": 2, "type": "post", "link": "https://demo.example/post/", "title": {"rendered": "Demo"}, "content": {"rendered": "<p>Demo content</p>"}, "categories": [1], "tags": [1]}]
            assert rest_base == "media"
            return []

        def close(self):
            pass

    monkeypatch.setattr("seo_brain.wordpress.sync.WordPressClient", WordPress)
    try:
        stats = sync_wordpress(conn, SiteConfig("demo", "Demo", "https://demo.example/", "https://demo.example"), use_auth=False, progress=progress)
        assert not failures, failures  # callback exceptions are swallowed by sync, so inspect explicitly.
        assert ("categories", {"taxonomy": "category"}) in progress_steps
        assert network_steps == ["categories", "tags", "posts", "media"]
        assert stats["taxonomies"] == {"category": 1, "post_tag": 1}
        assert stats["posts"] == 1 and stats["errors"] == []
        assert conn.execute("SELECT status FROM sync_runs WHERE run_id=?", (stats["run_id"],)).fetchone()[0] == "completed"
        assert conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM tags").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM post_terms").fetchone()[0] == 2
        assert conn.execute("SELECT COUNT(*) FROM writer_probes").fetchone()[0] == len(progress_steps) + len(network_steps)
    finally:
        conn.close()
        engine.dispose()
