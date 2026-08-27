import httpx

from seo_brain.common.google_http import ProxyAwareGoogleHttp, _proxy_from_environment


class _Credentials:
    def before_request(self, request, method, uri, headers):
        headers["authorization"] = "Bearer test-token"


class _Client:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def request(self, method, uri, headers=None, content=None):
        self.calls.append((method, uri, headers, content))
        result = next(self.responses)
        if isinstance(result, Exception):
            raise result
        return result

    def close(self):
        pass


def _response(status=200, body=b'{"ok":true}'):
    return httpx.Response(status, content=body, headers={"content-type": "application/json"})


def test_transport_adds_auth_and_returns_googleapiclient_response():
    transport = ProxyAwareGoogleHttp(_Credentials(), max_attempts=1)
    fake = _Client([_response()])
    transport._client = fake

    response, content = transport.request("https://google.test/v1/items", method="POST", body=b"{}")

    assert response.status == 200 and response.reason == "OK"
    assert content == b'{"ok":true}'
    assert fake.calls[0][2]["authorization"] == "Bearer test-token"


def test_transport_retries_transient_network_failure(monkeypatch):
    transport = ProxyAwareGoogleHttp(_Credentials(), max_attempts=2)
    fake = _Client([httpx.ConnectError("temporary"), _response()])
    transport._client = fake
    monkeypatch.setattr("seo_brain.common.google_http.time.sleep", lambda _: None)

    response, _ = transport.request("https://google.test/v1/items")

    assert response.status == 200 and len(fake.calls) == 2


def test_proxy_selection_ignores_unsupported_legacy_socks(monkeypatch):
    for name in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("ALL_PROXY", "socks4://127.0.0.1:10808")

    assert _proxy_from_environment() is None


def test_proxy_selection_prefers_explicit_https_proxy(monkeypatch):
    monkeypatch.setenv("ALL_PROXY", "socks4://127.0.0.1:10808")
    monkeypatch.setenv("HTTPS_PROXY", "http://bridge.local:18080")

    assert _proxy_from_environment() == "http://bridge.local:18080"
