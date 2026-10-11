"""The WordPress-only route must retain verified TLS and leave site crawls alone."""
from __future__ import annotations

import httpx
import pytest

from seo_brain.wordpress.origin import PinnedWordPressTransport, wordpress_rest_transport


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
