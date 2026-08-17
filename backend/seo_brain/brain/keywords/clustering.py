"""Keyword clustering — deterministic, offline, explainable.

Similarity = IDF-weighted Jaccard over stop-word-free tokens (0.7) + rapidfuzz token_set_ratio (0.3).
IDF (log(N/df)) makes tokens shared by almost every keyword (e.g. «امداد خودرو» on a towing site) nearly
weightless, so clusters form around the discriminating tokens (model, city, service).
Greedy agglomerative: iterate keywords by descending volume/length, attach to the best existing cluster whose
centroid similarity ≥ threshold, else start a new cluster. Cluster name = the shortest member; topic defaults to
the most frequent token(s) shared by ≥ half of the members. Manual clusters (`m-*`) are kept as-is.
"""
from __future__ import annotations

import hashlib
import math
from collections import Counter
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .normalize import tokenize
from .repository import Keyword, KeywordCluster


@dataclass
class _Cluster:
    members: list[Keyword] = field(default_factory=list)
    tokens: Counter = field(default_factory=Counter)

    def sim(self, toks: list[str], text: str, idf: dict[str, float]) -> float:
        if not self.tokens:
            return 0.0
        a, b = set(toks), set(self.tokens)
        w = lambda t: idf.get(t, 1.0)  # noqa: E731
        inter = sum(w(t) for t in a & b)
        union = sum(w(t) for t in a | b)
        jac = inter / union if union else 0.0
        centroid_text = " ".join(t for t, _ in self.tokens.most_common(6))
        fz = fuzz.token_set_ratio(text, centroid_text) / 100.0
        return 0.7 * jac + 0.3 * fz


def _cid(name: str) -> str:
    return "c-" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]


def cluster_keywords(kws: list[Keyword], threshold: float = 0.42) -> tuple[list[KeywordCluster], dict[int, str | None]]:
    """Returns (clusters, assignment keyword_id → cluster_id). Keywords already in manual clusters (m-*) are preserved."""
    assignment: dict[int, str | None] = {}
    manual: dict[str, list[Keyword]] = {}
    auto_pool: list[Keyword] = []
    for k in kws:
        if k.cluster_id and k.cluster_id.startswith("m-"):
            manual.setdefault(k.cluster_id, []).append(k); assignment[k.id] = k.cluster_id  # type: ignore[index]
        else:
            auto_pool.append(k)
    auto_pool.sort(key=lambda k: (-(k.volume or 0), len(k.normalized)))
    # IDF over the pool: tokens present in (almost) every keyword carry no discriminating weight
    n = max(1, len(auto_pool))
    df: Counter = Counter()
    for k in auto_pool:
        df.update(set(tokenize(k.keyword)))
    idf = {t: math.log((n + 1) / (c + 0.5)) for t, c in df.items()}
    clusters: list[_Cluster] = []
    for k in auto_pool:
        toks = tokenize(k.keyword)
        best, best_s = None, 0.0
        for c in clusters:
            s = c.sim(toks, k.normalized, idf)
            if s > best_s:
                best, best_s = c, s
        if best is not None and best_s >= threshold:
            best.members.append(k); best.tokens.update(toks)
        else:
            c = _Cluster(members=[k], tokens=Counter(toks)); clusters.append(c)
    out: list[KeywordCluster] = []
    for c in clusters:
        name = min(c.members, key=lambda k: (len(k.normalized), k.normalized)).keyword
        cid = _cid(name)
        n = len(c.members)
        common = [t for t, cnt in c.tokens.most_common() if cnt >= max(1, n / 2)][:3]
        topic = " ".join(common) if common else name
        # user-set topics on members win (most common non-empty)
        user_topics = Counter(k.topic for k in c.members if k.topic)
        if user_topics:
            topic = user_topics.most_common(1)[0][0]
        for k in c.members:
            assignment[k.id] = cid  # type: ignore[index]
        out.append(KeywordCluster(site_id=c.members[0].site_id, cluster_id=cid, name=name, topic=topic, keywords_count=n, method="token_jaccard"))
    for cid, members in manual.items():
        topics = Counter(k.topic for k in members if k.topic)
        out.append(KeywordCluster(site_id=members[0].site_id, cluster_id=cid, name=min(members, key=lambda k: len(k.normalized)).keyword,
                                  topic=topics.most_common(1)[0][0] if topics else None, keywords_count=len(members), method="manual"))
    return out, assignment
