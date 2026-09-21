"""AI_PROXY / WP_PROXY point at an SSH tunnel (socks5://127.0.0.1:1080). When nothing listens there the helpers must
return None (direct connection) instead of handing httpx a dead proxy — otherwise every Claude/Grok test and every
WordPress call fails with ConnectError even though the machine has its own route."""
import socket

from seo_brain.common import http as h


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def test_proxy_falls_back_to_direct_when_tunnel_is_closed(monkeypatch):
    h._PROXY_CHECK_CACHE.clear()
    monkeypatch.setenv("AI_PROXY", f"socks5://127.0.0.1:{_free_port()}")
    monkeypatch.setenv("WP_PROXY", f"socks5://127.0.0.1:{_free_port()}")
    assert h.ai_proxy() is None and h.site_proxy() is None
    monkeypatch.delenv("AI_PROXY")
    assert h.ai_proxy() is None


def test_proxy_is_used_while_the_tunnel_listens(monkeypatch):
    h._PROXY_CHECK_CACHE.clear()
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    url = f"socks5://127.0.0.1:{srv.getsockname()[1]}"
    try:
        monkeypatch.setenv("AI_PROXY", url)
        assert h.ai_proxy() == url
        assert h.proxy_reachable(url) is True                      # cached answer
    finally:
        srv.close()
    h._PROXY_CHECK_CACHE.clear()
    assert h.ai_proxy() is None                                    # tunnel gone → direct again


def test_proxy_without_host_port_is_left_alone(monkeypatch):
    h._PROXY_CHECK_CACHE.clear()
    monkeypatch.setenv("AI_PROXY", "socks5h://tunnel")
    assert h.ai_proxy() == "socks5h://tunnel"


def test_ai_proxy_auto_picks_the_first_working_local_vpn_proxy(monkeypatch):
    h._AUTO_CACHE.clear()
    monkeypatch.setenv("AI_PROXY", "auto")
    monkeypatch.setattr(h, "_port_open", lambda port, timeout=0.25: port in (7890, 1080))
    tried: list[str] = []
    monkeypatch.setattr(h, "_proxy_works", lambda url: tried.append(url) or url == "socks5://127.0.0.1:1080")
    assert h.ai_proxy() == "socks5://127.0.0.1:1080"
    assert tried == ["http://127.0.0.1:7890", "socks5://127.0.0.1:7890", "http://127.0.0.1:1080", "socks5://127.0.0.1:1080"]
    tried.clear()
    assert h.ai_proxy() == "socks5://127.0.0.1:1080" and tried == []          # cached


def test_ai_proxy_auto_means_direct_when_no_vpn_client_runs(monkeypatch):
    h._AUTO_CACHE.clear()
    monkeypatch.setenv("AI_PROXY", "auto")
    monkeypatch.setattr(h, "_port_open", lambda port, timeout=0.25: False)
    assert h.ai_proxy() is None
    monkeypatch.setattr(h, "_port_open", lambda port, timeout=0.25: True)
    monkeypatch.setattr(h, "_proxy_works", lambda url: True)
    monkeypatch.setenv("WP_PROXY", "auto")                                      # auto is an AI_PROXY feature: sites stay direct
    assert h.site_proxy() is None
