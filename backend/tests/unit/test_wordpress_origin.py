"""The WordPress-only route must retain verified TLS and leave site crawls alone."""
from __future__ import annotations

import httpx
import pytest

from seo_brain.wordpress.client import WordPressClient
from seo_brain.wordpress.origin import (
    PinnedWordPressTransport,
    fresh_rest_params,
    require_fresh_rest_response,
    wordpress_rest_transport,
)


def test_wordpress_origin_pin_preserves_host_sni_and_redirect(monkeypatch):
    monkeypatch.setenv("WP_REST_PINNED_HOST", "api.salimore.com")
    monkeypatch.setenv("WP_REST_ORIGIN_HOST", "salimore.com")
    monkeypatch.setenv("WP_REST_ORIGIN_IP", "89.44.243.109")
    transport = wordpress_rest_transport("https://api.salimore.com/wp-json/")
    assert isinstance(transport, PinnedWordPressTransport)
    assert wordpress_rest_transport("https://unrelated.example/wp-json/") is None
    seen = []

    def respond(request: httpx.Request) -> httpx.Response:
        seen.append((request.url.host, request.headers["host"], request.extensions.get("sni_hostname")))
        if len(seen) == 1:
            return httpx.Response(302, headers={"Location": "https://salimore.com/wp-json/wp/v2/types"})
        return httpx.Response(200, json={"post": {}})

    transport._transport.close()
    transport._transport = httpx.MockTransport(respond)
    with httpx.Client(transport=transport, follow_redirects=True) as client:
        response = client.get("https://api.salimore.com/wp-json/")
    assert response.status_code == 200
    assert seen == [
        ("89.44.243.109", "salimore.com", "salimore.com"),
        ("89.44.243.109", "salimore.com", "salimore.com"),
    ]


def test_wordpress_origin_pin_requires_explicit_https_configuration(monkeypatch):
    monkeypatch.delenv("WP_REST_PINNED_HOST", raising=False)
    monkeypatch.delenv("WP_REST_ORIGIN_HOST", raising=False)
    monkeypatch.delenv("WP_REST_ORIGIN_IP", raising=False)
    assert wordpress_rest_transport("https://api.salimore.com/wp-json/") is None
    monkeypatch.setenv("WP_REST_ORIGIN_HOST", "salimore.com")
    with pytest.raises(ValueError, match="together"):
        wordpress_rest_transport("https://api.salimore.com/wp-json/")
    monkeypatch.setenv("WP_REST_PINNED_HOST", "api.salimore.com")
    monkeypatch.setenv("WP_REST_ORIGIN_IP", "89.44.243.109")
    with pytest.raises(ValueError, match="HTTPS"):
        wordpress_rest_transport("http://api.salimore.com/wp-json/")
    monkeypatch.setenv("WP_REST_ORIGIN_IP", "not-an-ip")
    with pytest.raises(ValueError):
        wordpress_rest_transport("https://api.salimore.com/wp-json/")


def test_uncached_rest_reads_are_scoped_and_reject_stale_success(monkeypatch):
    monkeypatch.setenv("WP_REST_FRESH_HOST", "salimore.com")
    url = "https://salimore.com/wp-json/wp/v2/posts"
    first = fresh_rest_params(url, {"per_page": 1})
    second = fresh_rest_params(url, {"per_page": 1})
    assert first["per_page"] == second["per_page"] == 1
    assert first["_seo_brain_refresh"] != second["_seo_brain_refresh"]
    assert fresh_rest_params("https://another.example/wp-json/", {"per_page": 1}) == {"per_page": 1}
    require_fresh_rest_response(url, httpx.Response(200, headers={"X-Cache-Status": "MISS"}))
    require_fresh_rest_response(url, httpx.Response(200))  # uncached routes omit the header
    with pytest.raises(RuntimeError, match="X-Cache-Status=STALE"):
        require_fresh_rest_response(url, httpx.Response(200, headers={"X-Cache-Status": "STALE"}))
    with pytest.raises(RuntimeError, match="X-Cache-Status=HIT"):
        require_fresh_rest_response(url, httpx.Response(200, headers={"X-Cache-Status": "HIT"}))


def test_wordpress_client_uses_freshness_guard_before_accepting_content(monkeypatch):
    monkeypatch.setenv("WP_REST_FRESH_HOST", "salimore.com")
    seen = []

    class FakeHttp:
        def get(self, url, *, params, api):
            seen.append((url, params, api))
            return httpx.Response(200, headers={"X-Cache-Status": "STALE"}, json=[])

    client = object.__new__(WordPressClient)
    client.base = "https://salimore.com/wp-json"
    client.http = FakeHttp()
    with pytest.raises(RuntimeError, match="STALE"):
        client.get_json("/wp/v2/posts", {"per_page": 1})
    assert seen[0][1]["per_page"] == 1
    assert seen[0][1]["_seo_brain_refresh"]
