from seo_brain.normalizer import normalize_url, is_same_site, strip_tracking_params

H = "example.com"


def test_trailing_slash_equivalence():
    assert normalize_url("https://example.com/page", site_host=H) == normalize_url("https://example.com/page/", site_host=H)
    assert normalize_url("https://example.com/page", site_host=H).endswith("/page/")


def test_file_extension_untouched():
    assert normalize_url("https://example.com/sitemap.xml", site_host=H) == "https://example.com/sitemap.xml"


def test_tracking_removed_meaningful_kept():
    u = normalize_url("https://example.com/x/?utm_source=a&utm_medium=b&page=2&fbclid=z", site_host=H)
    assert u == "https://example.com/x/?page=2"


def test_fragment_removed_and_case():
    assert normalize_url("https://example.com/A/#frag", site_host=H) == "https://example.com/A/"


def test_www_and_scheme_fold():
    assert normalize_url("https://example.com/mvm/", site_host=H) == "https://example.com/mvm/"


def test_duplicate_slashes():
    assert normalize_url("https://example.com//blog///x/", site_host=H) == "https://example.com/blog/x/"


def test_percent_encoding_persian_equivalence():
    enc = "https://example.com/blog/%d8%a7%d9%85%d8%af%d8%a7%d8%af-%d8%ae%d9%88%d8%af%d8%b1%d9%88-mvm/"
    dec = "https://example.com/blog/امداد-خودرو-mvm/"
    assert normalize_url(enc, site_host=H) == normalize_url(dec, site_host=H)
    # idempotent
    n = normalize_url(dec, site_host=H)
    assert normalize_url(n, site_host=H) == n


def test_external_untouched_host():
    assert normalize_url("http://example.org/a", site_host=H).startswith("http://example.org/")


def test_same_site():
    assert is_same_site("https://example.com/x", [H])
    assert not is_same_site("https://google.com/", [H])


def test_strip_tracking_sorts():
    assert strip_tracking_params("b=1&a=2&utm_term=x") == "a=2&b=1"
