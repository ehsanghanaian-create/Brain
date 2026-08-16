from src.normalizer import normalize_url, is_same_site, strip_tracking_params

H = "emdadmodiran.com"


def test_trailing_slash_equivalence():
    assert normalize_url("https://emdadmodiran.com/page", site_host=H) == normalize_url("https://emdadmodiran.com/page/", site_host=H)
    assert normalize_url("https://emdadmodiran.com/page", site_host=H).endswith("/page/")


def test_file_extension_untouched():
    assert normalize_url("https://emdadmodiran.com/sitemap.xml", site_host=H) == "https://emdadmodiran.com/sitemap.xml"


def test_tracking_removed_meaningful_kept():
    u = normalize_url("https://emdadmodiran.com/x/?utm_source=a&utm_medium=b&page=2&fbclid=z", site_host=H)
    assert u == "https://emdadmodiran.com/x/?page=2"


def test_fragment_removed_and_case():
    assert normalize_url("HTTPS://EMDADMODIRAN.COM/A/#frag", site_host=H) == "https://emdadmodiran.com/A/"


def test_www_and_scheme_fold():
    assert normalize_url("http://www.emdadmodiran.com/mvm/", site_host=H) == "https://emdadmodiran.com/mvm/"


def test_duplicate_slashes():
    assert normalize_url("https://emdadmodiran.com//blog///x/", site_host=H) == "https://emdadmodiran.com/blog/x/"


def test_percent_encoding_persian_equivalence():
    enc = "https://emdadmodiran.com/blog/%d8%a7%d9%85%d8%af%d8%a7%d8%af-%d8%ae%d9%88%d8%af%d8%b1%d9%88-mvm/"
    dec = "https://emdadmodiran.com/blog/امداد-خودرو-mvm/"
    assert normalize_url(enc, site_host=H) == normalize_url(dec, site_host=H)
    # idempotent
    n = normalize_url(dec, site_host=H)
    assert normalize_url(n, site_host=H) == n


def test_external_untouched_host():
    assert normalize_url("http://example.org/a", site_host=H).startswith("http://example.org/")


def test_same_site():
    assert is_same_site("https://www.emdadmodiran.com/x", [H])
    assert not is_same_site("https://google.com/", [H])


def test_strip_tracking_sorts():
    assert strip_tracking_params("b=1&a=2&utm_term=x") == "a=2&b=1"
