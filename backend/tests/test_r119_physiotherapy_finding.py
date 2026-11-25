"""R-119 (Javad 2026-11-25): Sedi finds physiotherapy clinics in any city / area like any other clinic. Matrix: phrasing x language x place, plus the
query wording, the retry variant, the ring chain's entity and the not-a-find-request guards. DB-free."""
import pytest

from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as web

FIND = [  # (message, city or None)
    ("یک فیزیوتراپی خوب در پردیس میخوام", "پردیس"),
    ("فیزیوتراپ در بومهن کجاست", "بومهن"),
    ("دنبال فیزیوتراپی در شیراز هستم", "شیراز"),
    ("فیزیوتراپی خوب در رودهن معرفی کن", "رودهن"),
    ("کلینیک فیزیوتراپی در تهرانپارس", "تهران"),
    ("مرکز فیزیوتراپی نزدیک پیروزی تهران پیشنهاد بده", "تهران"),
    ("physiotherapist in Shiraz", "Shiraz"),
    ("find a physiotherapy clinic in Shiraz", "Shiraz"),
    ("I need a physical therapist in Tehran", "Tehran"),
]
NOT_A_FIND = [
    "فیزیوتراپی برای کمر درد چطوره؟",
    "فیزیوتراپی کنم خوبه؟",
    "my physiotherapist said to rest",
]


@pytest.mark.parametrize("message,city", FIND)
def test_a_physiotherapy_request_is_a_clinic_request_for_that_service_in_that_place(message, city):
    assert cn.is_care_navigation_query(message), message
    req = cn.parse_care_nav_request(message, language="fa")
    assert req.entity is cn.CareNavEntity.SPECIALTY_CENTER and req.specialty_or_service == "فیزیوتراپی", message
    assert req.city == city or req.area, message


@pytest.mark.parametrize("message", NOT_A_FIND)
def test_talking_about_physiotherapy_is_not_a_find_request(message):
    assert not cn.is_care_navigation_query(message), message


def test_the_query_names_the_place_the_way_people_do_and_has_a_second_name_to_retry():
    q = web.build_query("SPECIALTY_CENTER", "فیزیوتراپی", "پردیس", "تهران")
    assert q == "کلینیک فیزیوتراپی در پردیس, تهران"
    variants = web._query_variants(q, "SPECIALTY_CENTER", "IR")
    assert variants[0] == q and "مرکز فیزیوتراپی در پردیس, تهران" in variants
    assert web.build_query("SPECIALTY_CENTER", "فیزیوتراپی", None, None, area="تهرانپارس") == "کلینیک فیزیوتراپی در تهرانپارس"
    assert web.build_query("SPECIALTY_CENTER", None, "پردیس", "تهران").startswith("کلینیک یا مرکز درمانی")          # no service: the old plain wording
    assert web.build_query("SPECIALIST", "گوارش", "پردیس", "تهران") == "متخصص گوارش در پردیس, تهران"                  # doctors unchanged
    assert "کلینیک" not in web.build_query("SPECIALTY_CENTER", "فیزیوتراپی", "شیراز", "فارس", country="US")      # the Persian wording is for Iran only


def test_the_nearest_area_chain_works_for_a_physiotherapy_request(monkeypatch):
    from types import SimpleNamespace

    from backend.app.services.i5 import nearby_places as nb

    tried = []

    def query(db, request):
        tried.append((request.entity, request.specialty_or_service, request.area or request.city))
        ok = (request.area or request.city) == "پردیس"
        return cn.CareNavResult(status=cn.STATUS_VERIFIED if ok else cn.STATUS_NO_VERIFIED, entity=request.entity,
                                identities=tuple(SimpleNamespace() for _ in range(2 if ok else 0)), user_message="LIST")

    monkeypatch.setattr(cn, "query_governed_directory", query)
    monkeypatch.setattr(nb, "nearby_rings", lambda origin, **k: [["رودهن", "پردیس"]])
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service="فیزیوتراپی", city="بومهن", province="تهران", language="fa")
    out = cn._nearest_area_result(None, req, cn.CareNavResult(status=cn.STATUS_NO_VERIFIED, entity=req.entity, user_message="none"))
    assert out.status == cn.STATUS_VERIFIED
    assert tried == [(cn.CareNavEntity.SPECIALTY_CENTER, "فیزیوتراپی", "رودهن"), (cn.CareNavEntity.SPECIALTY_CENTER, "فیزیوتراپی", "پردیس")]  # same service, nearer places first


def test_the_nine_listing_sites_javad_named_are_trusted_and_look_alikes_are_not():
    for host in ("darmankade.com", "tabibyab.com", "lab.e-teb.com", "iranclinics.org", "clinicnekoo.ir", "www.behtarino.com", "irangaah.ir", "clinicroza.ir", "darooha.com"):
        assert web.is_trusted_url(f"https://{host}/x", "IR"), host
    assert not web.is_trusted_url("https://clinicnekoo.ir.evil.example/x", "IR")
    assert not web.is_trusted_url("https://fekrazadeh.ir/x", "IR")                                                # unlisted until Javad names it


@pytest.mark.parametrize("message", ["Explain physiology in pregnancy", "find a doctor specializing in electrophysiology in Tehran", "what is neurophysiology?"])
def test_physiology_words_are_not_physiotherapy(message):
    assert not cn._PHYSIO_PAT.search(message), message
    assert cn.detect_care_nav_entity(message) is not cn.CareNavEntity.SPECIALTY_CENTER


def _center_row(name, specialty=None):
    return {"canonical_directory_key": name, "id": name, "record_state": "ACTIVE", "canonical_name": name, "entity_type": "MEDICAL_CENTER",
            "specialty_or_service": specialty, "city": "پردیس", "province": "تهران", "source_system_label": "GOVERNED", "last_verified_at": None}


def test_an_unrelated_medical_centre_is_not_a_physiotherapy_result_and_does_not_stop_the_web_search(monkeypatch):
    rows = [_center_row("مرکز درمانی الف"), _center_row("مرکز درمانی ب"), _center_row("کلینیک فیزیوتراپی نور")]
    monkeypatch.setattr(cn, "_dispatch_governed_search", lambda db, request: rows)
    monkeypatch.setattr(cn, "_map_backend_row", lambda item: cn.VerifiedDirectoryIdentity(
        directory_record_id=1, entity_type="MEDICAL_CENTER", canonical_name=item["canonical_name"], canonical_directory_key=item["id"],
        specialty_or_service=item["specialty_or_service"], city="پردیس", province="تهران", source_system_label="GOVERNED", record_state="ACTIVE",
        last_verified_at=None, endorsement_disclaimer=""))
    web_calls = []
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: True)
    monkeypatch.setattr(cn, "_web_identities", lambda request: web_calls.append(1) or ())
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service="فیزیوتراپی", city="پردیس", province="تهران", language="fa")
    out = cn.query_governed_directory(None, req)
    assert [i.canonical_name for i in out.identities] == ["کلینیک فیزیوتراپی نور"]                       # only the centre that names the service
    assert web_calls == [1]                                                                              # one match is below MIN_LOCAL_HITS: the web search still runs
    plain = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service=None, city="پردیس", province="تهران", language="fa")
    assert len(cn.query_governed_directory(None, plain).identities) == 3                                 # no service asked: every centre counts, as before


def test_a_matching_centre_after_many_unrelated_ones_is_still_found(monkeypatch):
    seen = {}
    names = [f"مرکز درمانی {i:02d}" for i in range(8)] + ["کلینیک فیزیوتراپی نور"]                       # the matching one sorts LAST by name

    def search_hospitals(db, **k):
        seen["limit"] = k["limit"]
        return [_center_row(n) for n in names][: k["limit"]]

    monkeypatch.setattr(cn._governed_directory, "search_hospitals", search_hospitals)
    monkeypatch.setattr(cn, "_map_backend_row", lambda item: cn.VerifiedDirectoryIdentity(
        directory_record_id=1, entity_type="MEDICAL_CENTER", canonical_name=item["canonical_name"], canonical_directory_key=item["id"],
        specialty_or_service=None, city="پردیس", province="تهران", source_system_label="GOVERNED", record_state="ACTIVE",
        last_verified_at=None, endorsement_disclaimer=""))
    monkeypatch.setattr(cn._web_lookup, "web_lookup_enabled", lambda: False)
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service="فیزیوتراپی", city="پردیس", province="تهران", language="fa")
    out = cn.query_governed_directory(None, req)
    assert seen["limit"] >= 9 and [i.canonical_name for i in out.identities] == ["کلینیک فیزیوتراپی نور"]
    plain = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALTY_CENTER, specialty_or_service=None, city="پردیس", province="تهران", language="fa")
    cn.query_governed_directory(None, plain)
    assert seen["limit"] == plain.limit                                                                   # no service: the limit is untouched


def test_web_results_for_a_physiotherapy_request_must_name_the_service(monkeypatch):
    rows = [{"name": "کلینیک قلب نور", "specialty": "قلب و عروق"}, {"name": "مرکز فیزیوتراپی و توانبخشی شفا", "specialty": None},
            {"name": "کلینیک تخصصی البرز", "specialty": "فیزیوتراپی و طب فیزیکی"}, {"name": "کلینیک دندانپزشکی ماه", "specialty": "دندانپزشکی"}]
    kept = web._only_the_specialty(rows, "SPECIALTY_CENTER", "فیزیوتراپی")
    assert [r["name"] for r in kept] == ["مرکز فیزیوتراپی و توانبخشی شفا", "کلینیک تخصصی البرز"]
    assert web._only_the_specialty(rows, "SPECIALTY_CENTER", None) == rows                                 # no service asked: nothing filtered
    assert web._only_the_specialty(rows, "SPECIALTY_CENTER", "برچسب ناشناخته") == rows                    # an unknown label never filters
    assert web._only_the_specialty(rows, "LABORATORY", "فیزیوتراپی") == rows                                # other kinds untouched
    monkeypatch.setenv(web.SPEC_FILTER_DISABLED_ENV, "1")
    assert web._only_the_specialty(rows, "SPECIALTY_CENTER", "فیزیوتراپی") == rows                          # the existing kill switch covers it


def test_the_search_retries_when_the_first_answer_is_an_unrelated_clinic(monkeypatch):
    calls = []
    answers = [[{"name": "کلینیک قلب نور", "specialty": "قلب", "city": "پردیس", "address": "پردیس، خیابان ۱", "phone": "021-33445566",
                 "source_url": "https://darmankade.com/a"}],
               [{"name": "مرکز فیزیوتراپی شفا", "specialty": "فیزیوتراپی", "city": "پردیس", "address": "پردیس، خیابان ۲", "phone": "021-33445577",
                 "source_url": "https://darmankade.com/b"}]]
    monkeypatch.setenv(web.FLAG, "1")
    monkeypatch.setattr(web, "_take_quota", lambda: True)
    web._cache.clear()
    monkeypatch.setattr(web, "_call_web_search", lambda q, c, client=None: calls.append(q) or (answers.pop(0) if answers else []))
    monkeypatch.setattr(web, "verify_and_rank", lambda results, **k: results)
    out = web.search_web_providers(entity="SPECIALTY_CENTER", specialty="فیزیوتراپی", city="پردیس", province="تهران")
    assert [r["name"] for r in out] == ["مرکز فیزیوتراپی شفا"] and len(calls) == 2                       # the cardiology clinic did not end the search
