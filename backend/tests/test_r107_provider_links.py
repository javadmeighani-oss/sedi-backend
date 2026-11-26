"""R-107 am.3 (Javad 2026-11-21): the links of a doctor introduction are shown OUTSIDE the chat bubble (blue lines, opening the original site).

Backend half: the directory result carries `links` (built only from the verified result's own page or the directory's search pages),
the orchestrator result and the chat response expose them, and an app that says `supports_links` gets the bubble text without raw URLs.
DB-free."""
from types import SimpleNamespace

import pytest

from backend.app import sedi_copy
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import directory_web_lookup as web
from backend.app.services.i5 import provider_links as pl
from backend.app.services.intelligence.contracts import OrchestrationResult


def _ident(name, url):
    return SimpleNamespace(canonical_name=name, source_url=url)


# --- what may be a link ------------------------------------------------------------------------------------------------------------------------------
@pytest.mark.parametrize("url,ok", [
    ("https://www.paziresh24.com/dr/ali-alavi/", True),
    ("https://drdr.ir/doctors/x?city=teh", True),
    ("http://www.paziresh24.com/dr/x", False),                       # https only
    ("javascript:alert(1)", False), ("data:text/html,<b>x</b>", False), ("file:///etc/passwd", False), ("intent://x#Intent;end", False),
    ("https://user:pass@evil.example/x", False),                       # credentials
    ("https://nodot/x", False), ("https:///x", False), ("", False), (None, False),
    ("https://a.ir/x y", False), ("https://a.ir/<script>", False), ("https://a.ir/" + "x" * 700, False),
])
def test_only_a_safe_https_url_can_become_a_link(url, ok):
    assert (pl.safe_url(url) is not None) is ok


@pytest.mark.parametrize("lang,expected", [("fa", "پذیرش۲۴"), ("en", "Paziresh24"), ("ar", "Paziresh24")])
def test_the_site_is_named_in_the_users_language(lang, expected):
    assert pl.site_name("https://www.paziresh24.com/dr/x", lang) == expected
    assert pl.site_name("https://sub.drdr.ir/x", "fa") == "دکتر دکتر" and pl.site_name("https://clinic.example.ir/x", "fa") == "clinic.example.ir"


def test_each_verified_doctor_gets_the_link_of_his_own_page():
    items = pl.links_for_identities([
        _ident("دکتر الف", "https://www.paziresh24.com/dr/alef/"),
        _ident("دکتر ب", "https://drdr.ir/doctors/be"),
        _ident("دکتر الف", "https://www.paziresh24.com/dr/alef/"),     # the same page twice
        _ident("دکتر ج", None),                                         # a governed row without a page: no link
        _ident("دکتر د", "http://insecure.example.ir/x"),               # not https
    ], "fa")
    assert [(i["label"], i["kind"], i["host"]) for i in items] == [
        ("دکتر الف — پذیرش۲۴", "provider", "paziresh24.com"), ("دکتر ب — دکتر دکتر", "provider", "drdr.ir")]
    assert items[0]["url"] == "https://www.paziresh24.com/dr/alef/"


def test_at_most_five_links():
    many = [_ident(f"دکتر {i}", f"https://www.paziresh24.com/dr/{i}") for i in range(9)]
    assert len(pl.links_for_identities(many, "fa")) == pl.MAX_LINKS


def test_the_search_pages_are_links_when_nothing_verified_was_found():
    req = cn.CareNavRequest(entity=cn.CareNavEntity.SPECIALIST, specialty_or_service="گوارش", city="پردیس", language="fa")
    items = pl.links_for_search(cn.directory_search_links(req), "fa")
    assert [i["kind"] for i in items] == ["search", "search"] and items[0]["label"] == "جست‌وجو در پذیرش۲۴" and items[1]["label"] == "جست‌وجو در دکترتو"
    assert all(i["url"].startswith("https://") for i in items)


# --- the bubble text ---------------------------------------------------------------------------------------------------------------------------------
LINKS = [{"label": "دکتر الف — پذیرش۲۴", "url": "https://www.paziresh24.com/dr/alef/", "kind": "provider", "host": "paziresh24.com"}]


def test_the_raw_url_leaves_the_bubble_and_one_line_points_below():
    text = "چند مورد پیدا کردم:\n• دکتر الف — گوارش، پردیس؛ آدرس: خیابان اصلی؛ منبع: https://www.paziresh24.com/dr/alef/\nقبل از رفتن تماس بگیر."
    out = pl.strip_urls(text, LINKS, "fa")
    assert "https://" not in out and "منبع" not in out and "آدرس: خیابان اصلی" in out and "• دکتر الف — گوارش، پردیس" in out
    assert out.endswith(sedi_copy.t("care_nav.links.below", "fa")) and out.count(sedi_copy.t("care_nav.links.below", "fa")) == 1


def test_a_line_that_was_only_a_link_disappears():
    search = [{"label": "جست‌وجو در پذیرش۲۴", "url": "https://www.paziresh24.com/s/?text=x", "kind": "search", "host": "paziresh24.com"}]
    text = "چیزی تأییدشده پیدا نشد.\n• پذیرش۲۴: https://www.paziresh24.com/s/?text=x\nکدام تخصص؟"
    out = pl.strip_urls(text, search, "fa")
    assert "https://" not in out and "• پذیرش۲۴" not in out and "کدام تخصص؟" in out


@pytest.mark.parametrize("lang", ["fa", "ar", "en"])
def test_the_pointer_line_exists_in_every_language(lang):
    out = pl.strip_urls("A\nB: https://www.paziresh24.com/dr/alef/", LINKS, lang)
    assert out.endswith(sedi_copy.t("care_nav.links.below", lang)) and "{" not in out


def test_a_text_without_those_urls_is_unchanged():
    assert pl.strip_urls("سلام", LINKS, "fa") == "سلام" and pl.strip_urls("x https://other.ir/a", LINKS, "fa") == "x https://other.ir/a"
    assert pl.strip_urls("x", [], "fa") == "x"


def test_the_chat_api_returns_links_always_and_strips_the_text_only_for_an_app_that_supports_them():
    text = "• دکتر الف؛ منبع: https://www.paziresh24.com/dr/alef/"
    old_app = pl.reply_with_links(text, LINKS, None, "fa")
    new_app = pl.reply_with_links(text, LINKS, True, "fa")
    assert old_app[0] == text and old_app[1] == LINKS                          # an old app still gets the URL in the text (and ignores `links`)
    assert "https://" not in new_app[0] and new_app[1] == LINKS
    assert pl.reply_with_links("سلام", None, True, "fa") == ("سلام", None) and pl.reply_with_links("سلام", [], True, "fa") == ("سلام", None)


# --- the directory result ---------------------------------------------------------------------------------------------------------------------------
def _web_identity(name, url):
    return cn.VerifiedDirectoryIdentity(
        directory_record_id=0, entity_type="DOCTOR", canonical_name=name, canonical_directory_key="web_lookup:x:1", specialty_or_service="گوارش",
        city="پردیس", province=None, source_system_label="web_lookup", record_state="ACTIVE", last_verified_at=None, endorsement_disclaimer="",
        source_url=url, web_trusted=True)


def test_a_verified_result_carries_the_link_of_its_page(monkeypatch):
    ident = _web_identity("دکتر الف", "https://www.paziresh24.com/dr/alef/")
    monkeypatch.setattr(cn, "query_governed_directory", lambda db, r: cn.CareNavResult(
        status=cn.STATUS_VERIFIED, entity=cn.CareNavEntity.SPECIALIST, identities=(ident,), user_message="LIST"))
    out = cn.resolve_care_navigation(None, "یه دکتر گوارش در شهر پردیس معرفی کن", language="fa")
    assert [l["label"] for l in out.links] == ["دکتر الف — گوارش — پذیرش۲۴"] and out.links[0]["url"] == "https://www.paziresh24.com/dr/alef/"


def test_a_not_found_answer_carries_the_search_page_links(monkeypatch):
    monkeypatch.setattr(web, "web_lookup_enabled", lambda: False)
    monkeypatch.setattr(cn, "query_governed_directory", lambda db, r: cn.CareNavResult(
        status=cn.STATUS_NO_VERIFIED, entity=cn.CareNavEntity.SPECIALIST, user_message=cn.no_result_message_for(r)))
    out = cn.resolve_care_navigation(None, "یه دکتر گوارش در شهر پردیس معرفی کن", language="fa")
    assert out.status == cn.STATUS_NO_VERIFIED and [l["kind"] for l in out.links] == ["search", "search"]
    stripped, links = pl.reply_with_links(out.user_message, out.links, True, "fa")
    assert "https://" not in stripped and links == list(out.links)               # the not-found bubble loses its raw link lines too


def test_a_governed_row_without_a_page_has_no_link(monkeypatch):
    governed = cn.VerifiedDirectoryIdentity(
        directory_record_id=7, entity_type="DOCTOR", canonical_name="دکتر ب", canonical_directory_key="p24:7", specialty_or_service="گوارش", city="پردیس",
        province=None, source_system_label="P24", record_state="ACTIVE", last_verified_at=None, endorsement_disclaimer="")
    monkeypatch.setattr(cn, "query_governed_directory", lambda db, r: cn.CareNavResult(
        status=cn.STATUS_VERIFIED, entity=cn.CareNavEntity.SPECIALIST, identities=(governed,), user_message="LIST"))
    assert cn.resolve_care_navigation(None, "یه دکتر گوارش در شهر پردیس معرفی کن", language="fa").links == ()


# --- the orchestrator result ----------------------------------------------------------------------------------------------------------------------------
def _orch_result(**kw):
    base = dict(message="m", language="fa", request_id="r", contract_version="v", rollout_mode="compatibility", reason_codes=(), stage_names=())
    base.update(kw)
    return OrchestrationResult(**base)


def test_the_public_dict_carries_links_only_when_there_are_some():
    assert "links" not in _orch_result().public_brain_dict()
    out = _orch_result(links=tuple(LINKS)).public_brain_dict()
    assert out["links"] == LINKS and out["message"] == "m"


def test_the_chat_schemas_accept_the_new_fields_and_stay_backward_compatible():
    from datetime import datetime

    from backend.app.schemas.chat import ChatRequest
    from backend.app.schemas.interaction import InteractionResponse

    assert ChatRequest(message="سلام").supports_links is None and ChatRequest(message="سلام", supports_links=True).supports_links is True
    resp = InteractionResponse(message="m", language="fa", timestamp=datetime.utcnow(), links=LINKS)
    assert resp.model_dump(mode="json")["links"] == LINKS and InteractionResponse(message="m", language="fa", timestamp=datetime.utcnow()).links is None


# --- through the real orchestrator (real session) ---------------------------------------------------------------------------------------------------------
from backend.tests.test_r108_care_loop_e2e import _fixed_timezone, db, user  # noqa: E402,F401  (real-session fixtures)


def test_the_orchestrator_result_carries_the_links_of_a_doctor_turn_and_only_of_it(db, user, monkeypatch):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator

    def fake_resolve(db_, message, *, language, authenticated_user_id=None, **k):
        return SimpleNamespace(user_message="• دکتر الف؛ منبع: https://www.paziresh24.com/dr/alef/", status=cn.STATUS_VERIFIED, links=tuple(LINKS))

    monkeypatch.setattr(cn, "resolve_care_navigation", fake_resolve)
    monkeypatch.setattr(IntelligenceOrchestrator, "_journey_intake", lambda self, message, lang, user_id, said=None: None)  # the care interview is not what this test is about
    orch = IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    doctor = orch.process(authenticated_user_id=user.id, message="یه دکتر پوست در شیراز پیدا کن", language="fa")
    assert doctor.links == tuple(LINKS) and doctor.public_brain_dict()["links"] == LINKS and "paziresh24.com/dr/alef" in doctor.message
    chat = orch.process(authenticated_user_id=user.id, message="سلام حالت چطوره", language="fa")
    assert chat.links == () and "links" not in chat.public_brain_dict()


def test_p2_a_sparse_provider_entry_keeps_its_name_specialty_and_city():
    text = "• دکتر الف — گوارش، پردیس؛ منبع: https://www.paziresh24.com/dr/alef/\n• پذیرش۲۴: https://www.paziresh24.com/s/?text=x"
    links = LINKS + [{"label": "جست‌وجو در پذیرش۲۴", "url": "https://www.paziresh24.com/s/?text=x", "kind": "search", "host": "paziresh24.com"}]
    out = pl.strip_urls(text, links, "fa")
    assert "• دکتر الف — گوارش، پردیس" in out and "https://" not in out and "• پذیرش۲۴" not in out      # the entry stays, the link-only line goes
    assert pl.strip_urls("https://www.paziresh24.com/dr/alef/", LINKS, "fa").startswith(sedi_copy.t("care_nav.links.below", "fa")[:10])


# --- Codex round 1 on PR 214: the links are kept with the stored turn and come back in the history -----------------------------------------------------------------
def test_p2_the_links_are_stored_with_the_turn_and_returned_by_the_history(db, user, monkeypatch):
    from backend.app.routers.interact import get_user_history
    from backend.app.services.i7.governed_raw import attach_reply_links, links_of_turn
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    from backend.app import models

    reply = "• دکتر الف؛ آدرس: خیابان اصلی"
    monkeypatch.setattr(cn, "resolve_care_navigation", lambda *a, **k: SimpleNamespace(user_message=reply, status=cn.STATUS_VERIFIED, links=tuple(LINKS)))
    monkeypatch.setattr(IntelligenceOrchestrator, "_journey_intake", lambda self, message, lang, user_id, said=None: None)
    orch = IntelligenceOrchestrator(db=db, legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)
    orch.process(authenticated_user_id=user.id, message="یه دکتر پوست در شیراز پیدا کن", language="fa")
    from backend.app.core.conversation.memory import ConversationMemory

    assert ConversationMemory(db).save_conversation(user.id, "سلام", "سلام!", "fa") is not None   # an ordinary turn, stored by the brain
    rows = db.query(models.Memory).filter(models.Memory.user_id == user.id).order_by(models.Memory.id).all()
    assert [bool(links_of_turn(r)) for r in rows] == [True, False]                   # only the doctor turn carries links
    history = get_user_history(user=user, user_id=None, limit=10, db=db)["messages"]
    with_links = [m for m in history if m.get("links")]
    assert len(with_links) == 1 and with_links[0]["links"][0]["url"] == LINKS[0]["url"] and with_links[0]["sedi_response"] == reply
    assert all("links" not in m for m in history if m is not with_links[0])           # a plain turn keeps the old shape


def test_p2_attaching_links_is_fail_open_and_ignores_junk(db, user):
    from backend.app.services.i7.governed_raw import attach_reply_links, links_of_turn

    assert attach_reply_links(db, user_id=user.id, sedi_response="never stored", links=LINKS) is False        # no such turn
    assert attach_reply_links(db, user_id=user.id, sedi_response="x", links=[]) is False
    assert attach_reply_links(db, user_id=user.id, sedi_response="", links=LINKS) is False
    assert links_of_turn(SimpleNamespace(provenance_json="not json")) == [] and links_of_turn(SimpleNamespace(provenance_json=None)) == []
    assert links_of_turn(SimpleNamespace(provenance_json='{"links": "x"}')) == []
