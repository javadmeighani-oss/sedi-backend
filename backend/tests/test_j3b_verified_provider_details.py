"""J3-b (D-407): SSRF-safe page reads, field-by-field verification of what the search model claimed, ranking, «why this one»."""
import pytest

from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as wl
from backend.app.services.i5 import page_facts as pf
from backend.app.services.i5 import safe_fetch as sf


# ---------------------------------------------------------------- SSRF guard
def _res(*ips):
    return lambda host: list(ips)


@pytest.mark.parametrize("url, reason", [
    ("http://example.com/x", "not_https"), ("ftp://example.com", "not_https"), ("https://user:pw@example.com/", "credentials_in_url"),
    ("https://example.com:8443/", "port_not_allowed"), ("https://127.0.0.1/", "ip_literal"), ("https://[::1]/", "ip_literal"),
    ("https://localhost/", "bad_host"), ("https://printer.local/", "internal_name"), ("https://db.internal/x", "internal_name"),
    ("", "not_https"), ("not a url", "not_https"),
])
def test_urls_that_must_never_be_fetched(url, reason):
    assert sf.validate_url(url, _res("93.184.216.34"))[2] == reason


@pytest.mark.parametrize("ip", ["127.0.0.1", "10.0.0.5", "172.16.3.4", "192.168.1.9", "169.254.169.254", "0.0.0.0", "100.64.1.1",
                                "::1", "fe80::1", "fc00::1", "::ffff:127.0.0.1", "224.0.0.1", "240.0.0.1"])
def test_a_host_resolving_to_a_non_public_address_is_refused(ip):
    assert sf.validate_url("https://clinic.example.ir/x", _res(ip))[2] == "non_public_address"


def test_one_private_address_among_public_ones_refuses_the_host():
    assert sf.validate_url("https://clinic.example.ir/", _res("93.184.216.34", "10.1.1.1"))[2] == "non_public_address"


def test_a_public_host_is_allowed_and_pinned_to_its_validated_address():
    host, ip, reason = sf.validate_url("https://www.paziresh24.com/dr/x", _res("93.184.216.34"))
    assert (host, ip, reason) == ("www.paziresh24.com", "93.184.216.34", "")


def test_dns_failure_is_a_clean_refusal():
    def boom(host):
        raise OSError("nxdomain")

    assert sf.validate_url("https://nope.example.ir/", boom)[2] == "dns_failed"


def _fetch_with(monkeypatch, pages, resolver=None):
    """pages: url -> (status, headers, body, ctype); robots.txt answers 404 unless listed."""
    calls = []

    def fake_once(host, ip, path, timeout, deadline=None):
        calls.append((host, ip, path))
        key = f"https://{host}{path}"
        if path == "/robots.txt" and key not in pages:
            return 404, {}, b"", "text/plain"
        return pages[key]

    monkeypatch.setattr(sf, "_get_once", fake_once)
    sf._robots_cache.clear()
    return calls, (resolver or _res("93.184.216.34"))


def test_a_page_is_read_and_a_redirect_is_followed_and_revalidated(monkeypatch):
    calls, res = _fetch_with(monkeypatch, {
        "https://a.example.ir/p": (302, {"location": "https://b.example.ir/q"}, b"", "text/html"),
        "https://b.example.ir/q": (200, {}, "<html>سلام</html>".encode(), "text/html")})
    out = sf.fetch_page("https://a.example.ir/p", resolver=res)
    assert out.ok and out.url == "https://b.example.ir/q" and "سلام" in out.body.decode()
    assert all(ip == "93.184.216.34" for _h, ip, _p in calls)


def test_a_redirect_to_a_private_host_is_refused_on_the_second_hop(monkeypatch):
    def resolver(host):
        return ["10.0.0.7"] if host == "evil.example.ir" else ["93.184.216.34"]

    _c, _r = _fetch_with(monkeypatch, {"https://a.example.ir/p": (301, {"location": "https://evil.example.ir/secret"}, b"", "text/html")})
    out = sf.fetch_page("https://a.example.ir/p", resolver=resolver)
    assert not out.ok and out.reason == "non_public_address"


def test_a_redirect_to_http_or_a_metadata_url_is_refused(monkeypatch):
    _c, res = _fetch_with(monkeypatch, {"https://a.example.ir/p": (302, {"location": "http://169.254.169.254/latest/meta-data"}, b"", "text/html")})
    assert sf.fetch_page("https://a.example.ir/p", resolver=res).reason == "not_https"


def test_a_redirect_loop_stops(monkeypatch):
    _c, res = _fetch_with(monkeypatch, {"https://a.example.ir/p": (302, {"location": "https://a.example.ir/p"}, b"", "text/html")})
    assert sf.fetch_page("https://a.example.ir/p", resolver=res).reason == "too_many_redirects"


@pytest.mark.parametrize("page, reason", [
    ((200, {}, b"%PDF", "application/pdf"), "content_type"), ((200, {}, b"x", "too_large"), "too_large"),
    ((404, {}, b"", "text/html"), "http_404"), ((503, {}, b"", "text/html"), "http_503")])
def test_unusable_responses_are_clean_failures(monkeypatch, page, reason):
    _c, res = _fetch_with(monkeypatch, {"https://a.example.ir/p": page})
    out = sf.fetch_page("https://a.example.ir/p", resolver=res)
    assert not out.ok and out.reason == reason


def test_robots_txt_is_honoured(monkeypatch):
    _c, res = _fetch_with(monkeypatch, {
        "https://a.example.ir/robots.txt": (200, {}, b"User-agent: *\nDisallow: /private/\n", "text/plain"),
        "https://a.example.ir/private/x": (200, {}, b"secret", "text/html"),
        "https://a.example.ir/public/x": (200, {}, b"ok", "text/html")})
    assert sf.fetch_page("https://a.example.ir/private/x", resolver=res).reason == "robots_disallow"
    assert sf.fetch_page("https://a.example.ir/public/x", resolver=res).ok


def test_fetch_never_raises(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("socket exploded")

    monkeypatch.setattr(sf, "_get_once", boom)
    sf._robots_cache.clear()
    out = sf.fetch_page("https://a.example.ir/p", resolver=_res("93.184.216.34"))
    assert not out.ok


# ---------------------------------------------------------------- field verification
PAGE = """<html><body><h1>دکتر علی رضایی</h1>
<p>آدرس: تهران، پاسداران، بین بوستان نهم و دهم، مجتمع بوستان، پلاک ۲۹۷</p>
<p>تلفن: ۰۲۱-۲۲۷۹ ۲۶۹۴</p><p>ساعات ویزیت: شنبه تا دوشنبه ساعت ۱۶ تا ۲۰ و چهارشنبه ساعت ۹</p>
<p>امتیاز ۴.۵ از ۵ (۱۲۰ نظر) — مطب شبانه‌روزی نیست</p></body></html>"""


def _item(**kw):
    base = {"name": "دکتر علی رضایی", "specialty": "قلب", "city": "تهران", "address": "پاسداران، بین بوستان نهم و دهم، مجتمع بوستان، پلاک 297",
            "phone": "02122792694", "source_url": "https://clinic.example.ir/dr", "visit_days": ["شنبه", "چهارشنبه", "جمعه"],
            "rating": "4.5", "rating_count": "120"}
    base.update(kw)
    return base


def _ok(html):
    return lambda url: sf.FetchResult(True, url, 200, html.encode("utf-8"))


def _bad(reason="http_403"):
    return lambda url: sf.FetchResult(False, url, 403, reason=reason)


def test_a_phone_that_is_on_the_page_is_verified_in_any_digit_form():
    v = pf.verify_result(_item(), fetch=_ok(PAGE))
    assert v.read and v.phone == "02122792694" and v.phone_status == "verified" and v.address_verified


def test_a_phone_that_is_not_on_the_page_is_rejected_and_never_shown():
    v = pf.verify_result(_item(phone="02133334444"), fetch=_ok(PAGE))
    assert v.read and v.phone is None and v.phone_status == "rejected"


def test_an_unreadable_page_keeps_the_claim_but_marks_it_unchecked():
    v = pf.verify_result(_item(), fetch=_bad())
    assert not v.read and v.phone == "02122792694" and v.phone_status == "unchecked" and v.checked_on is None


def test_a_published_mobile_number_is_accepted_when_the_page_shows_it():
    html = PAGE.replace("۰۲۱-۲۲۷۹ ۲۶۹۴", "۰۹۱۲ ۳۴۵ ۶۷۸۹")
    v = pf.verify_result(_item(phone="09123456789"), fetch=_ok(html))
    assert v.phone == "09123456789" and v.phone_status == "verified"


@pytest.mark.parametrize("raw", ["", "0", "123", "00000000000", "05100000000", "1111111111"])
def test_placeholders_and_fragments_are_not_phones(raw):
    assert pf.published_phone(raw) is None


def test_an_address_the_page_does_not_contain_is_dropped():
    v = pf.verify_result(_item(address="شیراز، خیابان زند، پلاک ۵"), fetch=_ok(PAGE))
    assert v.address is None and not v.address_verified


def test_only_days_the_page_shows_next_to_a_time_are_kept():
    v = pf.verify_result(_item(), fetch=_ok(PAGE))
    assert v.visit_days == ("شنبه", "چهارشنبه")  # «جمعه» was claimed but is not on the page


def test_a_day_inside_another_day_name_is_not_confused():
    assert pf.days_on_page(["شنبه"], "نوبت یکشنبه ساعت ۱۰") == ()
    assert pf.days_on_page(["سه شنبه"], "سه‌شنبه ساعت ۱۷") == ("سه‌شنبه",)


def test_a_rating_needs_both_number_and_count_on_the_page():
    v = pf.verify_result(_item(), fetch=_ok(PAGE))
    assert v.rating_avg == 4.5 and v.rating_count == 120
    v2 = pf.verify_result(_item(rating="4.9", rating_count="33"), fetch=_ok(PAGE))
    assert v2.rating_avg is None and v2.rating_count is None


def test_the_paziresh24_page_wins_over_the_model(monkeypatch):
    monkeypatch.setattr(pf, "_p24", lambda raw, city=None: {"phone": "02122792694", "address": "پاسداران - مجتمع بوستان - پلاک 297", "rating_avg": 4.4, "rating_count": 140})
    html = '<html>"freeturn_text":"یک‌شنبه ساعت 05:10"</html>'
    v = pf.verify_result(_item(phone="02100000001", source_url="https://www.paziresh24.com/dr/x"),
                         fetch=lambda url: sf.FetchResult(True, "https://www.paziresh24.com/dr/x", 200, html.encode()))
    assert v.phone == "02122792694" and v.phone_status == "verified" and v.rating_avg == 4.4 and v.rating_count == 140
    assert v.next_turn == "یک‌شنبه ساعت 05:10" and v.address_verified


def test_verification_never_raises():
    def boom(url):
        raise RuntimeError("x")

    v = pf.verify_result(_item(), fetch=boom)
    assert not v.read


# ---------------------------------------------------------------- ranking + why
def _row(name, **kw):
    base = {"name": name, "specialty": "قلب", "city": "تهران", "address": "پاسداران، پلاک 297", "phone": "02122792694",
            "source_url": f"https://{name}.example.ir/", "trusted": False, "visit_days": [], "rating": "", "rating_count": ""}
    base.update(kw)
    return base


def test_a_page_that_was_read_and_confirms_nothing_is_dropped():
    out = wl.verify_and_rank([_row("a", phone="02100000009", address="جای دیگر، خیابان دیگر")], specialty="قلب", area=None, fetch=_ok(PAGE))
    assert out == []


def test_an_unreadable_page_keeps_the_result_marked_unchecked():
    out = wl.verify_and_rank([_row("a")], specialty="قلب", fetch=_bad())
    assert len(out) == 1 and out[0]["phone_status"] == "unchecked" and out[0]["page_read"] is False


def test_the_verified_result_ranks_above_the_unverified_one_and_says_why():
    rows = [_row("unread"), _row("read", source_url="https://read.example.ir/")]

    def fetch(url):
        return sf.FetchResult(True, url, 200, PAGE.encode()) if "read.example" in url and "unread" not in url else sf.FetchResult(False, url, reason="blocked")

    out = wl.verify_and_rank(rows, specialty="قلب", area="پاسداران", fetch=fetch)
    assert [r["name"] for r in out] == ["read", "unread"]
    assert "page_checked" in out[0]["why"] and "area" in out[0]["why"] and "spec" in out[0]["why"]


def test_high_rating_and_24h_qualifiers_change_the_order():
    good = PAGE.replace("شبانه‌روزی نیست", "شبانه‌روزی")
    rows = [_row("plain", source_url="https://plain.example.ir/", rating="4.5", rating_count="120"), _row("open", source_url="https://open.example.ir/", rating="4.5", rating_count="120")]
    out = wl.verify_and_rank(rows, specialty="قلب", qualifiers=("24h", "high_rating"),
                             fetch=lambda url: sf.FetchResult(True, url, 200, (good if "open" in url else PAGE.replace("شبانه‌روزی نیست", "")).encode()))
    assert out[0]["name"] == "open" and "open24" in out[0]["why"] and "rating" in out[0]["why"]


def test_the_page_check_has_a_kill_switch(monkeypatch):
    monkeypatch.setenv("SEDI_DIRECTORY_PAGE_VERIFY_DISABLED", "true")
    out = wl.verify_and_rank([_row("a")], specialty="قلب", fetch=_ok(PAGE))
    assert out[0]["phone_status"] == "unchecked" and out[0]["phone"] == "02122792694"


# ---------------------------------------------------------------- what the user reads
def _identity(**kw):
    base = dict(directory_record_id=0, entity_type="DOCTOR", canonical_name="دکتر رضایی", canonical_directory_key="k", specialty_or_service="قلب",
                city="تهران", province=None, source_system_label="web_lookup", record_state="ACTIVE", last_verified_at=None,
                endorsement_disclaimer="x", phone="02122792694", address="پاسداران", source_url="https://www.paziresh24.com/dr/x", web_trusted=True)
    base.update(kw)
    return cn.VerifiedDirectoryIdentity(**base)


def test_the_reply_shows_days_next_turn_rating_checked_date_and_why():
    h = _identity(phone_status="verified", visit_days=("شنبه", "چهارشنبه"), next_turn="یک‌شنبه ساعت 05:10", rating_avg=4.5, rating_count=120,
                  checked_on="2026-11-19", why=("spec", "area", "page_checked"))
    msg = cn._serialize_hits_message([h], "fa", True)  # the source, the check date and «why» appear when the user asked for the source
    for needle in ("تلفن: 02122792694", "روزهای ویزیت طبق صفحه: شنبه، چهارشنبه", "نزدیک‌ترین نوبت طبق صفحه: یک‌شنبه ساعت 05:10",
                   "امتیاز 4.5 از ۵ (120 نظر)", "بررسی صفحه: 2026-11-19", "چرا این گزینه:", "تخصصش با درخواستت می‌خواند", "در محله‌ی مورد نظرت است"):
        assert needle in msg


def test_an_unchecked_phone_is_labelled_not_verified_in_every_language():
    for lang, label in (("fa", "تأییدنشده"), ("en", "not verified"), ("ar", "غير مؤكد")):
        msg = cn._serialize_hits_message([_identity(phone_status="unchecked", web_trusted=False)], lang)
        assert label in msg


def test_the_reply_without_the_new_facts_is_unchanged():
    msg = cn._serialize_hits_message([_identity()], "fa")
    assert "چرا این گزینه" not in msg and "روزهای ویزیت" not in msg and "تأییدنشده): " not in msg


# ---------------------------------------------------------------- Codex review of PR 190
def test_p2_a_different_area_code_is_never_verified_by_a_suffix_match():
    runs = pf.page_digit_runs("تلفن: 02122792694")
    assert pf.phone_on_page("02122792694", runs)
    assert not pf.phone_on_page("03122792694", runs)  # same last 8 digits, another city
    assert not pf.phone_on_page("02522792694", runs)


@pytest.mark.parametrize("claimed", ["02122792694", "+982122792694", "00982122792694", "2122792694", "021 2279 2694"])
def test_p2_every_equivalent_format_of_the_full_number_verifies(claimed):
    assert pf.phone_on_page(claimed, pf.page_digit_runs("تماس: ۰۲۱-۲۲۷۹۲۶۹۴"))


def test_p2_two_numbers_written_next_to_each_other_do_not_break_verification():
    runs = pf.page_digit_runs("تلفن: 02122792694  02133445566")
    assert pf.phone_on_page("02122792694", runs) and pf.phone_on_page("02133445566", runs)
    assert not pf.phone_on_page("02144445555", runs)


def test_p2_a_mobile_number_is_compared_in_full_too():
    runs = pf.page_digit_runs("موبایل: 0912 345 6789")
    assert pf.phone_on_page("09123456789", runs) and not pf.phone_on_page("09223456789", runs)


def test_p2_unrelated_digits_are_not_a_rating():
    html = "<html>Telephone: 02122792694. Address: 512 Main St. Open 5 days.</html>"
    v = pf.verify_result(_item(rating="5", rating_count="12", address="512 Main St"), fetch=_ok(html))
    assert v.rating_avg is None and v.rating_count is None


def test_p2_a_rating_next_to_rating_words_is_evidence():
    v = pf.verify_result(_item(rating="4.5", rating_count="120"), fetch=_ok(PAGE))
    assert v.rating_avg == 4.5 and v.rating_count == 120


@pytest.mark.parametrize("text", ["مطب شبانه‌روزی نیست", "این مرکز شبانه‌روزی ندارد", "not open 24 hours", "غیر شبانه‌روزی"])
def test_p2_a_negated_24h_statement_is_not_24h(text):
    assert not pf._affirmative_24h(pf._fold(text))


@pytest.mark.parametrize("text", ["این داروخانه شبانه‌روزی است", "open 24 hours", "خدمات ۲۴ ساعته", "درمانگاه شبانه‌روزی"])
def test_p2_an_affirmative_24h_statement_is_24h(text):
    assert pf._affirmative_24h(pf._fold(text))


def test_p2_the_test_fixture_page_that_says_not_24h_does_not_boost_24h():
    v = pf.verify_result(_item(), fetch=_ok(PAGE))
    assert v.open_24h is False


def test_p2_a_slow_body_is_cut_by_the_absolute_deadline(monkeypatch):
    """A server trickling bytes must not hold the reply: the whole read has ONE deadline."""
    import time

    class Resp:
        status = 200

        def getheaders(self):
            return [("Content-Type", "text/html")]

        def read(self, n):
            time.sleep(0.05)
            return b"x" * 10

    class Conn:
        def __init__(self, *a, **k): pass
        def request(self, *a, **k): pass
        def getresponse(self): return Resp()
        def close(self): pass

    monkeypatch.setattr(sf, "_PinnedHTTPS", Conn)
    start = time.time()
    status, _h, body, ctype = sf._get_once("a.example.ir", "93.184.216.34", "/", 5.0, deadline=time.time() + 0.2)
    assert ctype == "timeout" and body == b"" and time.time() - start < 1.5


def test_p2_the_robots_request_shares_the_deadline(monkeypatch):
    seen = []

    def fake_once(host, ip, path, timeout, deadline=None):
        seen.append((path, deadline))
        return (404, {}, b"", "text/plain") if path == "/robots.txt" else (200, {}, b"ok", "text/html")

    monkeypatch.setattr(sf, "_get_once", fake_once)
    sf._robots_cache.clear()
    out = sf.fetch_page("https://a.example.ir/p", resolver=_res("93.184.216.34"))
    assert out.ok and all(d is not None for _p, d in seen)


def test_p2_a_timeout_during_the_body_is_a_clean_failure(monkeypatch):
    monkeypatch.setattr(sf, "_get_once", lambda *a, **k: (200, {}, b"", "timeout") if a[2] != "/robots.txt" else (404, {}, b"", "text/plain"))
    sf._robots_cache.clear()
    out = sf.fetch_page("https://a.example.ir/p", resolver=_res("93.184.216.34"))
    assert not out.ok and out.reason == "timeout"


# ---- Codex round 2: a doctor with offices in several cities
def _p24_html(centers):
    import json

    props = {"information": {"display_name": "علی رضایی"}, "slug": "dr-x-1", "centers": centers,
             "expertises": {"expertises": [{"alias_title": "متخصص قلب"}]},
             "feedbacks": {"details": {"average_rates": {"a": 4.5}, "count_of_feedbacks": 120}}}
    return ('<html><script id="__NEXT_DATA__" type="application/json">' + json.dumps({"props": {"pageProps": props}}, ensure_ascii=False)
            + "</script></html>").encode("utf-8")


SHIRAZ = {"id": "1", "type_id": 1, "is_active": True, "city": "شیراز", "address": "شیراز، خیابان زند، پلاک ۵", "tell": ["07133334444"]}
TEHRAN = {"id": "2", "type_id": 1, "is_active": True, "city": "تهران", "address": "تهران، پاسداران، پلاک ۲۹۷", "tell": ["02122792694"]}


def test_p2_the_office_in_the_requested_city_is_used_not_the_first_one():
    t = pf._p24(_p24_html([SHIRAZ, TEHRAN]), "تهران")
    assert t["phone"] == "02122792694" and "پاسداران" in t["address"] and t["rating_avg"] == 4.5 and t["rating_count"] == 120
    s = pf._p24(_p24_html([SHIRAZ, TEHRAN]), "شیراز")
    assert s["phone"] == "07133334444"


def test_p2_a_doctor_without_an_office_in_the_requested_city_gives_no_page_truth():
    assert pf._p24(_p24_html([SHIRAZ]), "تهران") == {}


def test_p2_the_tehran_claim_never_becomes_the_shiraz_contact():
    html = _p24_html([SHIRAZ, TEHRAN])
    v = pf.verify_result(_item(phone="02122792694", city="تهران", source_url="https://www.paziresh24.com/dr/x"),
                         fetch=lambda url: sf.FetchResult(True, "https://www.paziresh24.com/dr/x", 200, html))
    assert v.phone == "02122792694" and "پاسداران" in (v.address or "")
    only_shiraz = _p24_html([SHIRAZ])
    v2 = pf.verify_result(_item(phone="02122792694", city="تهران", source_url="https://www.paziresh24.com/dr/x"),
                          fetch=lambda url: sf.FetchResult(True, "https://www.paziresh24.com/dr/x", 200, only_shiraz))
    assert v2.phone != "07133334444" and v2.phone_status in ("rejected", "none")


# ---- Codex round 3: closed days and ranges
def test_p2_a_day_the_page_marks_closed_is_not_a_visit_day():
    page = "ساعات کاری مطب: شنبه تا پنجشنبه ۹ تا ۱۷. جمعه تعطیل است."
    assert pf.days_on_page(["جمعه"], page) == ()
    assert pf.days_on_page(["شنبه", "پنجشنبه", "جمعه"], page) == ("شنبه", "پنجشنبه")


def test_p2_a_range_on_the_page_opens_every_day_between():
    page = "ویزیت: شنبه تا چهارشنبه ساعت ۱۶ تا ۲۰"
    assert pf.days_on_page(["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه"], page) == ("شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه")


@pytest.mark.parametrize("page", ["جمعه: تعطیل", "ویزیت جمعه ندارد، ساعت کاری ۹ تا ۱۲", "Friday closed, hours 9 to 12"])
def test_p2_closure_wordings_are_all_respected(page):
    assert pf.days_on_page(["جمعه"], page) == ()


def test_p2_an_open_day_with_a_closed_neighbour_stays_open():
    assert pf.days_on_page(["شنبه", "جمعه"], "شنبه ساعت ۹ تا ۱۲؛ جمعه تعطیل") == ("شنبه",)


def test_the_source_the_check_date_and_why_are_hidden_unless_the_user_asked_for_the_source():
    h = _identity(phone_status="verified", visit_days=("شنبه",), checked_on="2026-11-19", why=("spec", "area"))
    quiet = cn._serialize_hits_message([h], "fa")
    assert "https://" not in quiet and "منبع:" not in quiet and "بررسی صفحه" not in quiet and "چرا این گزینه" not in quiet
    assert "تلفن: 02122792694" in quiet and "روزهای ویزیت طبق صفحه: شنبه" in quiet  # the useful facts stay
    asked = cn._serialize_hits_message([h], "fa", True)
    assert "https://www.paziresh24.com/dr/x" in asked and "بررسی صفحه: 2026-11-19" in asked and "چرا این گزینه" in asked


def test_an_unchecked_phone_label_stays_even_when_the_source_is_hidden():
    assert "تأییدنشده" in cn._serialize_hits_message([_identity(phone_status="unchecked", web_trusted=False)], "fa")
