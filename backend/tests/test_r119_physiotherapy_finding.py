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
