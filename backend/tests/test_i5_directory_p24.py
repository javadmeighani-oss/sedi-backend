"""Paziresh24 public directory parsing (offline, trimmed real structure)."""
import json
from types import SimpleNamespace

from backend.app.services.i5.iran_directory_normalization import normalize_records
from backend.app.services.i5.iran_directory_p24 import (
    P24_SOURCE, classify_facility, clean_landline, crawl_doctors, parse_center_page, parse_doctor_page, parse_sitemap,
)


def _page(props):
    data = json.dumps({"props": {"pageProps": props}}, ensure_ascii=False)
    return f'<html><script id="__NEXT_DATA__" type="application/json">{data}</script></html>'


def _center(**kw):
    base = {"id": "c-1", "name": "مطب دکتر الف", "tell": ["074-33221477", "09391185911"], "address": "یاسوج، 60 متری",
            "type_id": 1, "city": "یاسوج", "province": "کهگیلویه و بویراحمد", "is_active": True}
    return {**base, **kw}


def _doctor(centers, slug="دکتر-الف", name="الف ب"):
    return _page({"slug": slug, "information": {"display_name": name},
                  "expertises": {"expertises": [{"alias_title": "فوق تخصص گوارش"}]}, "centers": centers})


def test_clean_landline_drops_mobile_and_normalizes():
    assert clean_landline(["09391185911"]) is None
    assert clean_landline("09391185911", "074-33221477") == "07433221477"
    assert clean_landline("2188052167") == "02188052167"
    assert clean_landline("۰۲۱۲۲۰۰۱۰۷۲") == "0212200107" + "2"
    assert clean_landline("1234") is None
    assert clean_landline("05100000000") is None


def test_classify_facility_by_name_not_platform_type():
    assert classify_facility("بیمارستان امید") == ("HOSPITAL", "HOSPITAL")
    assert classify_facility("کلینیک تخصصی دندان") == ("HOSPITAL", "MEDICAL_CENTER")
    assert classify_facility("آزمایشگاه تشخیص طبی")[0] == "LABORATORY"
    assert classify_facility("مطب دکتر الف") is None


def test_doctor_record_uses_landline_only_and_attribution_key():
    doc, facs = parse_doctor_page(_doctor([_center()]))
    assert doc["phone"] == "07433221477" and doc["address"] == "یاسوج، 60 متری" and doc["city"] == "یاسوج"
    assert doc["specialty"] == "فوق تخصص گوارش" and doc["source_system_label"] == P24_SOURCE
    assert doc["canonical_directory_key"].startswith(P24_SOURCE + ":dr:") and facs == []
    valid, rej = normalize_records([doc])
    assert len(valid) == 1 and not rej


def test_inactive_bulk_center_address_is_kept_and_online_center_ignored():
    online = _center(id="c-2", name="ویزیت آنلاین", type_id=3, address="آنلاین")
    doc, _ = parse_doctor_page(_doctor([online, _center(is_active=False, tell=[])]))
    assert doc["address"] == "یاسوج، 60 متری" and doc["phone"] is None


def test_hospital_center_inside_doctor_page_becomes_facility():
    hosp = _center(id="h-1", name="بیمارستان شهید بهشتی تفت", type_id=2, tell=["035-33668000"], city="تفت", province="یزد")
    _, facs = parse_doctor_page(_doctor([hosp]))
    assert facs[0]["entity_family"] == "HOSPITAL" and facs[0]["facility_type"] == "HOSPITAL"
    assert facs[0]["canonical_directory_key"] == f"{P24_SOURCE}:center:h-1"
    valid, rej = normalize_records(facs)
    assert len(valid) == 1 and not rej


def test_center_page_parse_and_office_is_skipped():
    q = lambda name: _page({"dehydratedState": {"queries": [{"queryKey": ["slugProfile", {}], "state": {"data": {"result": {
        "data": {"id": "x1", "name": name, "city": "ابهر", "province": "زنجان", "address": "شهرک", "tell": "02435279241"}}}}}]}})
    rec = parse_center_page(q("آزمایشگاه نور"))
    assert rec["entity_family"] == "LABORATORY" and rec["phone"] == "02435279241"
    assert parse_center_page(q("مطب دکتر ج")) is None
    assert parse_center_page("<html></html>") is None


def test_sitemap_parse():
    assert parse_sitemap("<urlset><url><loc>https://a/1</loc></url><url><loc>https://a/2&amp;x</loc></url></urlset>") == ["https://a/1", "https://a/2&x"]


def test_crawl_respects_budget_host_and_counts_failures():
    ok = "https://www.paziresh24.com/dr/%D8%AF%DA%A9%D8%AA%D8%B1-%D8%A7%D9%84%D9%81/"
    calls = []

    def get(url, **_):
        calls.append(url)
        if url.endswith("bad/"):
            raise OSError("down")
        return SimpleNamespace(status_code=200, content=_doctor([_center()]).encode(), url=url)

    urls = [ok, "https://evil.example/dr/x/", "https://www.paziresh24.com/dr/bad/", ok + "?2", ok + "?3"]
    res = crawl_doctors(urls, http_get=get, budget=3, interval=0, sleep=lambda s: None)
    assert res["stats"]["failed"] == 2 and res["stats"]["fetched"] == 1
    assert "https://evil.example/dr/x/" not in calls
    assert len(res["records"]) == 1


def test_doctor_without_address_or_phone_is_skipped():
    doc, _ = parse_doctor_page(_doctor([]))
    assert doc is None


def test_rolling_window_wraps_and_advances():
    from backend.scripts.iran_directory_p24_run import window

    urls = [f"u{i}" for i in range(10)]
    assert window(urls, 4, 0) == ["u0", "u1", "u2", "u3"]
    assert window(urls, 4, 1) == ["u4", "u5", "u6", "u7"]
    assert window(urls, 4, 2) == ["u8", "u9", "u0", "u1"]
    assert len(window(urls, 50, 3)) == 10 and window([], 4, 0) == []
