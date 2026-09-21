"""Phone-number change runbook: the operator fills two numbers, the platform derives every form the number is stored
in (Latin/Persian × separators, plus the escaped Persian that Elementor writes into _elementor_data) and the SQL."""
import pytest
from fastapi.testclient import TestClient

from seo_brain.api import deps
from seo_brain.api.main import create_app
from seo_brain.api.routers import sites as sites_router
from seo_brain.brain.ops.phone_change import PhoneChangeError, plan, to_escaped, to_fa
from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate

OLD, NEW = "02122477005", "02122144279"


@pytest.fixture
def c(tmp_path, monkeypatch):
    eng = make_engine("sqlite:///" + (tmp_path / "ops.db").as_posix()); migrate(eng)
    monkeypatch.delenv("API_TOKEN", raising=False)
    monkeypatch.setattr(sites_router, "PROJECT_ROOT", tmp_path)
    app = create_app(); app.dependency_overrides[deps.engine] = lambda: eng
    client = TestClient(app); client.eng = eng  # type: ignore[attr-defined]
    return client


def test_every_stored_form_is_derived():
    out = plan(OLD, NEW, "modirankhodro-emdad.com", db_name="kamandbe_emdad")
    assert out["old8"] == "22477005" and out["new8"] == "22144279"
    forms = {p["old"]: p["new"] for p in out["pairs"]}
    assert forms["22477005"] == "22144279" and forms["2247 7005"] == "2214 4279" and forms["2247-7005"] == "2214-4279"
    assert forms["۲۲۴۷۷۰۰۵"] == "۲۲۱۴۴۲۷۹" and forms["۲۲۴۷ ۷۰۰۵"] == "۲۲۱۴ ۴۲۷۹" and forms["۲۲۴۷-۷۰۰۵"] == "۲۲۱۴-۴۲۷۹"
    assert forms["\\u06f2\\u06f2\\u06f4\\u06f7\\u06f7\\u06f0\\u06f0\\u06f5"] == "\\u06f2\\u06f2\\u06f1\\u06f4\\u06f4\\u06f2\\u06f7\\u06f9"
    assert all(len(o) == len(n) for o, n in forms.items())                      # serialized data keeps its lengths
    sql = out["variables"]["sql_text"]
    for table in ("wp_posts", "wp_postmeta", "wp_options"):
        assert f"UPDATE `{table}`" in sql
    assert sql.count("REPLACE(") == 6 * 5                                       # six forms × five columns
    assert "REPLACE(meta_value, '\\\\u06f2" in out["variables"]["sql_escaped"]   # backslash doubled for SQL
    assert "_elementor_css" in out["variables"]["sql_cache"] and "transient" in out["variables"]["sql_cache"]
    assert out["variables"]["sql_verify"].count("UNION ALL") == 4 and "۲۲۴۷۷۰۰۵" in out["variables"]["sql_verify"]
    book = out["runbook"]
    assert "modirankhodro-emdad.com" in book and OLD in book and NEW in book and "kamandbe_emdad" in book
    assert "{{" not in book and "پشتیبان" in book                          # every variable filled, backup step kept
    assert book.count("22144279") >= 3 and "۲۲۱۴۴۲۷۹" in book


def test_unsafe_pairs_are_refused():
    for old, new in ((OLD, OLD), ("021", "02122144279"), ("", NEW), ("abc", "def")):
        with pytest.raises(PhoneChangeError):
            plan(old, new)


def test_endpoint_uses_the_site_and_the_prompt_library(c):
    assert c.post("/api/v1/sites", json={"site_id": "modiran", "name": "مدیران", "canonical_url": "https://modirankhodro-emdad.com/"}).status_code == 201
    r = c.post("/api/v1/tools/phone-change", json={"old_phone": OLD, "new_phone": NEW, "site_id": "modiran", "db_name": "kamandbe_emdad"})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["old8"] == "22477005" and d["new8"] == "22144279" and d["site"] == "modirankhodro-emdad.com"
    assert d["prompt_ref"] == "ops.phone_change@v1"                            # the text comes from the prompt library
    assert len(d["replacements"]) == 7 and "https://modirankhodro-emdad.com/" in d["runbook"]
    assert set(d["sql"]) == {"sql_text", "sql_escaped", "sql_cache", "sql_verify"}

    # editing the prompt in the platform changes what the tool returns (the prompts router builds its own library
    # from the Gateway engine, so the edit goes through the library on this test's engine)
    from seo_brain.ai.prompts.library import PromptLibrary
    library = PromptLibrary(c.eng)
    pid = next(p["id"] for p in library.list() if p["key"] == "ops.phone_change")
    library.add_version(pid, "فقط {{old8}} → {{new8}} روی {{site}}", activate=True)   # scope 'ops' → no memory_pack rule
    r2 = c.post("/api/v1/tools/phone-change", json={"old_phone": OLD, "new_phone": NEW, "site": "x.example"})
    assert r2.json()["runbook"] == "فقط 22477005 → 22144279 روی x.example"

    assert c.post("/api/v1/tools/phone-change", json={"old_phone": OLD, "new_phone": OLD, "site": "x.example"}).status_code == 422
    assert c.post("/api/v1/tools/phone-change", json={"old_phone": OLD, "new_phone": NEW, "site_id": "nope"}).status_code == 404


def test_persian_helpers():
    assert to_fa("22477005") == "۲۲۴۷۷۰۰۵" and to_escaped("05") == "\\u06f0\\u06f5"
