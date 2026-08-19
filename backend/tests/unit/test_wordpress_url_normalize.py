"""Unit tests for WordPress URL normalization/validation (seo_brain.common.urls).

Regression coverage for the bug where a value with no scheme (e.g. an Application
Password pasted into the "WordPress URL" field) was passed straight to httpx and
raised `UnsupportedProtocol` with a URL like `f6wOsgR8NahkD5waVkCHKxXu/wp-json/`.
"""
import pytest

from seo_brain.common.urls import InvalidWordPressUrlError, normalize_wordpress_url, wp_rest_root, wp_rest_v2


@pytest.mark.parametrize("raw,expected", [
    ("https://example.com", "https://example.com"),
    ("https://example.com/", "https://example.com"),
    ("http://example.com", "http://example.com"),
    ("example.com", "https://example.com"),           # bare domain -> https added
    ("www.example.com", "https://www.example.com"),
    ("example.com/blog", "https://example.com/blog"),
    ("example.com/blog/", "https://example.com/blog"),
    ("localhost:8080", "https://localhost:8080"),
    ("192.168.1.10", "https://192.168.1.10"),
    ("  example.com  ", "https://example.com"),        # trimmed
    ("https://example.com/wp-json/", "https://example.com"),          # REST root pasted → site base
    ("example.com/wp-json", "https://example.com"),
    ("https://example.com/blog/wp-json/wp/v2/", "https://example.com/blog"),
])
def test_normalize_accepts_and_fixes_valid_inputs(raw, expected):
    assert normalize_wordpress_url(raw) == expected


@pytest.mark.parametrize("raw", [
    None,
    "",
    "   ",
])
def test_normalize_rejects_empty(raw):
    with pytest.raises(InvalidWordPressUrlError):
        normalize_wordpress_url(raw)


def test_normalize_rejects_application_password_like_token():
    """The exact regression: a scheme-less, dot-less token must not become a hostname."""
    with pytest.raises(InvalidWordPressUrlError) as exc:
        normalize_wordpress_url("f6wOsgR8NahkD5waVkCHKxXu")
    msg = str(exc.value)
    assert "f6wOsgR8NahkD5waVkCHKxXu" not in msg  # never echo the secret-looking value verbatim
    assert "Application Password" in msg or "توکن" in msg


def test_normalize_rejects_value_with_spaces():
    # WordPress Application Passwords are typically rendered as "xxxx xxxx xxxx xxxx xxxx xxxx"
    with pytest.raises(InvalidWordPressUrlError):
        normalize_wordpress_url("abcd efgh ijkl mnop qrst uvwx")


def test_normalize_rejects_unsupported_scheme():
    with pytest.raises(InvalidWordPressUrlError):
        normalize_wordpress_url("ftp://example.com")


def test_normalize_rejects_credentials_in_url():
    with pytest.raises(InvalidWordPressUrlError):
        normalize_wordpress_url("https://admin:secretpass@example.com")


def test_rest_endpoint_builders():
    assert wp_rest_root("https://example.com") == "https://example.com/wp-json/"
    assert wp_rest_v2("https://example.com") == "https://example.com/wp-json/wp/v2/"
    # idempotent regardless of trailing slash on the input base
    assert wp_rest_root("https://example.com/") == "https://example.com/wp-json/"
    assert wp_rest_v2("https://example.com/") == "https://example.com/wp-json/wp/v2/"
