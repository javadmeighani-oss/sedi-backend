"""SBMU official per-facility page → address/phone (offline, trimmed real markup)."""
from types import SimpleNamespace

from backend.app.services.i5.iran_directory_federation import (
    acquire_sbmu_affiliated_hospitals,
    parse_sbmu_detail_links,
    parse_sbmu_facility_contact,
)

_ITEM = '<div class="place-map__item"><div class="icon"> <i class="x"></i> </div><div class="data text__14">{}</div>\n</div>'
_DETAIL = (
    '<div id="mapagency" data-address="تهران - خیابان شریعتی - بن بست آذر" ></div>'
    '<div class="place-map__content">' + _ITEM.format("تهران - خیابان شریعتی - بن بست آذر") + _ITEM.format("{phone}") + "</div>"
)


def test_contact_parses_address_and_phone_variants():
    for phone in ("22001072 - 021", "021-22227021-9", "02188902155الی 02188902159"):
        c = parse_sbmu_facility_contact(_DETAIL.replace("{phone}", phone))
        assert c == {"address": "تهران - خیابان شریعتی - بن بست آذر", "phone": phone}


def test_contact_missing_block_is_empty_not_guessed():
    assert parse_sbmu_facility_contact("<html>no map</html>") == {"address": None, "phone": None}


def test_detail_links_ignore_honorifics():
    html = '<a href="/Virtual_Tour/بیمارستان/امام-حسین-(ع)" aria-label="امام حسین (ع)" class="t">x</a>'
    links = parse_sbmu_detail_links(html)
    assert links["امام حسین"].startswith("https://sbmu.ac.ir/Virtual_Tour/")


def test_acquire_enriches_and_keeps_record_when_detail_fails():
    names = ["اختر", "مفید"]
    listing = "".join(f'<a href="/Virtual_Tour/بیمارستان/{n}" aria-label="{n}" class="t">{n}</a>' for n in names)
    from backend.app.services.i5.iran_directory_federation import SBMU_HOSPITAL_SEED
    listing += " ".join(s["name"] for s in SBMU_HOSPITAL_SEED)

    def getter(url, **_):
        if "%D9%85%D9%81%DB%8C%D8%AF" in url:  # مفید → detail page down
            raise OSError("timeout")
        if url.endswith("%D8%A7%D8%AE%D8%AA%D8%B1"):  # اختر detail page
            return SimpleNamespace(status_code=200, content=_DETAIL.replace("{phone}", "22001072 - 021").encode(), url=url)
        return SimpleNamespace(status_code=200, content=listing.encode(), url=url)

    res = acquire_sbmu_affiliated_hospitals(http_get=getter, detail_delay_seconds=0)
    by = {r["name"]: r for r in res.records}
    assert by["بیمارستان اختر"]["phone"] == "22001072 - 021"
    assert by["بیمارستان اختر"]["address"].startswith("تهران")
    assert "phone" not in by["بیمارستان مفید"]
    assert len(res.records) == len(SBMU_HOSPITAL_SEED)
