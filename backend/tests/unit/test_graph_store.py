import pytest

from seo_brain.db.engine import make_engine
from seo_brain.db.migrate import migrate
from seo_brain.db.repositories import SiteMemoryRepository, SitesRepository
from seo_brain.db.repositories.sites import Site
from seo_brain.graph.model import GraphEdge, GraphNode
from seo_brain.graph.store import GraphStore, SqlGraphStore


@pytest.fixture
def engine(tmp_path):
    eng = make_engine("sqlite:///" + (tmp_path / "g.db").as_posix())
    migrate(eng)
    SitesRepository(eng).save(Site(site_id="t", name="T", canonical_url="https://t.example/"))
    return eng


def test_store_roundtrip_neo4j_shape(engine):
    store = SqlGraphStore(engine)
    assert isinstance(store, GraphStore)
    nodes = [GraphNode("site:t", "t", "SITE", {"label": "T"}),
             GraphNode("page:https://t.example/a", "t", "PAGE", {"label": "A", "url": "https://t.example/a", "props": {"h1": ["x"]}}),
             GraphNode("query:امداد", "t", "QUERY", {"label": "امداد"})]
    edges = [GraphEdge("site:t", "page:https://t.example/a", "HAS_PAGE", site_id="t"),
             GraphEdge("page:https://t.example/a", "query:امداد", "RANKS_FOR", weight=0.7, site_id="t", metadata={"props": {"position": 7.9}})]
    assert store.upsert_nodes(nodes) == 3 and store.upsert_edges(edges) == 2
    assert store.upsert_nodes(nodes) == 3  # idempotent

    c = store.counts("t")
    assert c["nodes"] == 3 and c["edges"] == 2 and c["by_relation_type"]["RANKS_FOR"] == 1

    n = store.get_node("t", "page:https://t.example/a")
    assert n and n.type == "PAGE" and n.metadata["url"] == "https://t.example/a" and n.metadata["props"]["h1"] == ["x"]

    sg = store.subgraph("t", "site:t", hops=2)
    assert {x.id for x in sg.nodes} == {"site:t", "page:https://t.example/a", "query:امداد"}
    assert {(e.source, e.relation_type, e.target) for e in sg.edges} == {("site:t", "HAS_PAGE", "page:https://t.example/a"),
                                                                        ("page:https://t.example/a", "RANKS_FOR", "query:امداد")}
    e = [e for e in sg.edges if e.relation_type == "RANKS_FOR"][0]
    assert e.weight == 0.7 and e.metadata["props"]["position"] == 7.9

    nb = store.neighbors("t", "query:امداد", direction="in")
    assert len(nb.edges) == 1 and {x.id for x in nb.nodes} == {"query:امداد", "page:https://t.example/a"}
    assert [x.id for x in store.search("t", "امداد")] == ["query:امداد"]
    assert store.subgraph("t", "site:t", hops=0).nodes[0].id == "site:t"


def test_site_memory_repository(engine):
    repo = SiteMemoryRepository(engine)
    m = repo.get("t")
    assert m.business_rules == [] and m.updated_at is None
    m.business_rules = ["فقط خدمات امداد خودرو"]; m.tone = {"voice": "formal"}
    saved = repo.save(m)
    assert saved.business_rules == ["فقط خدمات امداد خودرو"] and saved.tone["voice"] == "formal" and saved.updated_at
    repo.add_pattern("t", "link to service page", "ctr up", "test")
    assert repo.get("t").successful_patterns[0]["pattern"] == "link to service page"


def test_sites_repository_modes(engine):
    repo = SitesRepository(engine)
    assert repo.get("t").mode == "manual"
    assert repo.set_mode("t", "assisted").mode == "assisted"
    with pytest.raises(ValueError):
        repo.set_mode("t", "yolo")
