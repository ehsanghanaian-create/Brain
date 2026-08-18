import sqlite3

from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import _split_statements, discover, migrate, migrate_sqlite, status


def test_discover_versions_are_ordered_and_unique():
    ms = discover()
    versions = [m.version for m in ms]
    assert versions == sorted(versions) and len(set(versions)) == len(versions)
    assert versions[:2] == ["0001", "0002"]


def test_split_keeps_statements_with_trailing_comments():
    sql = "ALTER TABLE t ADD COLUMN a TEXT;   -- comment; with semicolon\nCREATE VIEW v AS SELECT 'a;b' AS x;"
    parts = _split_statements(sql)
    assert len(parts) == 2 and parts[0].startswith("ALTER") and "'a;b'" in parts[1]


def test_migrate_fresh_sqlite_is_idempotent(tmp_path):
    conn = sqlite3.connect(tmp_path / "t.db")
    first = migrate_sqlite(conn)
    second = migrate_sqlite(conn)
    assert first[:2] == ["0001", "0002"] and "0003" in first and second == []
    cols = {r[1] for r in conn.execute("pragma table_info(sites)")}
    assert {"mode", "business_type", "country", "ga4_property", "workspace_path"} <= cols
    views = {r[0] for r in conn.execute("select name from sqlite_master where type='view'")}
    assert {"graph_nodes_v", "graph_edges_v"} <= views


def test_migrate_via_engine_and_status(tmp_path):
    eng = make_engine("sqlite:///" + (tmp_path / "e.db").as_posix())
    assert migrate(eng)[:7] == ["0001", "0002", "0003", "0004", "0005", "0006", "0007"]
    st = status(eng)
    assert all(s["applied"] for s in st) and len(st) >= 2
