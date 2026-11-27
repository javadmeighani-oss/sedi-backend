"""R-120 am.3 (Javad 2026-11-27, two phone tests): any answer to the open interview stays in the doctor chain (the pilot «چک اپ» fell out
and the free model invented a hotline); the follow-up questions come even when memory completed the request; the «as you said before» note
only when the place did not come from this conversation; no generic status question after the list; each doctor is numbered and carries the
phone the site publishes."""
import json
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from backend.app import sedi_copy
from backend.app.services.care_journey import followup_questions as fq
from backend.app.services.care_journey import journey as j
from backend.app.services.i5 import care_nav_interview as ci
from backend.app.services.i5 import care_navigation_directory as cn
from backend.app.services.i5 import provider_links as pl
from backend.app.services.i5 import site_readers as sr

REQ = "برام پزشک خوب پیدا کن متخصص قلب در تهران‌پارس تهران"
ASK = sedi_copy.t("journey.intake.lead", "fa") + "\n\n" + sedi_copy.t("journey.interview.chest", "fa")


@pytest.mark.parametrize("answer", ["چیز مهمی نیست فقط میخوام چک اپ بشم", "چک آپ", "چکاپ سالانه", "هیچی خاصی نیست", "فقط می‌خواهم توانایی‌هایت را ببینم",
                                    "دکترم گفت برو", "nothing special, just a check-up", "از دیروز درد دارم؟",
                                    "When I exercise", "When walking upstairs", "where it hurts is my chest", "دو ساعت"])
def test_any_answer_to_the_open_interview_stays_in_the_doctor_chain(answer):
    done = ci.request_for_answer(REQ, ASK, answer, "fa")
    assert done and cn.parse_care_nav_request(done, language="fa").specialty_or_service == "قلب", answer


@pytest.mark.parametrize("other", ["امروز هوا چطوره؟", "رمزم را چطور عوض کنم؟", "How do I change my password?", "فردا ساعت ۹ یادم بنداز",
                                   "How do I change my password", "Translate this sentence into Persian", "رمزم را چطور عوض کنم", "این جمله را ترجمه کن"])
def test_a_question_about_something_else_or_another_request_is_its_own_turn(other):
    assert ci.request_for_answer(REQ, ASK, other, "fa") is None


def test_the_results_block_never_ends_with_the_generic_status_question(monkeypatch):
    monkeypatch.setattr(j, "_journey_open", lambda *a, **k: True)
    block = j.results_block(MagicMock(), 7, REQ, "fa")
    assert block == sedi_copy.t("journey.care.chest", "fa") and sedi_copy.t("journey.status_only", "fa") not in block


def _orch(monkeypatch, rows):
    from backend.app.services.intelligence.orchestrator import IntelligenceOrchestrator
    import backend.app.services.i6.consent_service as consent
    import backend.app.services.i7.retention as retention

    monkeypatch.setattr(consent, "has_permission", lambda *a, **k: True)
    monkeypatch.setattr(retention, "query_eligible_raw", lambda *a, limit=None, **k: list(rows)[: (limit or 60)])
    return IntelligenceOrchestrator(db=MagicMock(), legacy_generator=lambda *a, **k: {"message": "GEN", "detected_name": None}, structured_mode=False)


def test_the_follow_up_step_is_due_after_the_open_interview_even_when_memory_completed_the_request(monkeypatch):
    rows = [SimpleNamespace(user_message=REQ, sedi_response=ASK, created_at=datetime.utcnow())]
    orch = _orch(monkeypatch, rows)
    assert orch._answering_open_interview(42)
    rows[0].sedi_response = fq.followup_message("x", "fa")
    assert not orch._answering_open_interview(42)  # the second step is asked once


def test_the_place_note_is_left_out_when_he_named_the_place_in_this_conversation(monkeypatch):
    rows = [SimpleNamespace(user_message="میخوام برام یه متخصص قلب تو محله تهرانپارس معرفی کنی", sedi_response=ASK, created_at=datetime.utcnow())]
    orch = _orch(monkeypatch, rows)
    assert orch._place_said_now("تهران‌پارس تهران", 42, "فقط میخوام توانایی‌هایت را ببینم")
    assert not orch._place_said_now("پردیس", 42, "یه دکتر قلب خوب معرفی کن")


def test_replay_check_up_answer_reaches_the_follow_up_questions_not_the_free_model(monkeypatch):
    from backend.app.services.i10 import commitment_followup as cf

    monkeypatch.setenv(fq.DISABLED_ENV, "1")
    monkeypatch.setenv(sr.ENABLED_ENV, "0")
    monkeypatch.setattr(cf, "open_journey_count", lambda *a, **k: 1)
    searched, rows = [], []
    monkeypatch.setattr(cn._governed_directory, "search_doctors", lambda db_, **k: searched.append(k) or [])
    orch = _orch(monkeypatch, rows)

    def say(text):
        out = orch.process(authenticated_user_id=42, message=text, language="fa")
        rows.insert(0, SimpleNamespace(id=len(rows) + 1, user_message=text, sedi_response=out.message, created_at=datetime.utcnow()))
        return out

    say("برام یه متخصص قلب تو تهرانپارس تهران پیدا کن")
    follow = say("چیز مهمی نیست فقط میخوام چک اپ بشم")
    assert follow.message != "GEN" and j.is_followup_reply(follow.message)  # never the free model
    say("هیچ مشکلی ندارم")
    assert searched and searched[-1]["city"] == "تهران"


# --- numbered doctors with the phone the site publishes ---------------------------------------------------------------------------------------
def _page(items):
    data = {"props": {"pageProps": {"dehydratedState": {"queries": [{"queryKey": ["search"], "state": {"data": {"search": {"result": items, "total": len(items)}}}}]}}}}
    return ("<html><body><script id=\"__NEXT_DATA__\" type=\"application/json\">" + json.dumps(data, ensure_ascii=False) + "</script></body></html>").encode("utf-8")


def _doc(i, phone):
    return {"type": "doctor", "prefix": "دکتر", "display_name": f"قلب {i:02d}", "display_expertise": "متخصص قلب و عروق", "rates_count": 50 + i, "star": 4.5,
            "url": f"/dr/doc-{i:02d}/", "centers": [{"address": "شیراز، زند", "city_name": "شیراز", "display_number": phone, "map": {"lat": 29.6, "lon": 52.5}}]}


def test_each_doctor_is_numbered_and_carries_the_published_phone(monkeypatch):
    sr._cache.clear(), sr._verified.clear(), sr._areas.clear()
    monkeypatch.setattr(sr, "MIN_GAP_SECONDS", 0.0)
    monkeypatch.setenv(sr.VERIFY_ENV, "false")
    url = dict(sr.listing_urls("قلب", "شیراز"))["paziresh24.com"]
    items = [_doc(1, "071-32345678"), _doc(2, ""), _doc(3, "071-36212345")]
    rows = sr.provider_rows("قلب", "شیراز", fetch=lambda u: SimpleNamespace(ok=u == url, reason="", body=_page(items)))
    phones = {r["name"]: r["phone"] for r in rows}
    assert phones["دکتر قلب 01"].replace("-", "") == "07132345678" and phones["دکتر قلب 02"] is None and phones["دکتر قلب 03"]
    idents = [SimpleNamespace(source_url=f"https://www.paziresh24.com/dr/doc-{i}/", canonical_name=f"دکتر {i}", specialty_or_service="قلب",
                              address="شیراز", city="شیراز", note=None, phone=("071-32345678" if i == 1 else None)) for i in (1, 2, 3)]
    links = pl.links_for_identities(idents, "fa")
    assert [link["index"] for link in links] == [1, 2, 3] and links[0]["phone"] == "071-32345678" and "phone" not in links[1]
    sr._cache.clear(), sr._verified.clear(), sr._areas.clear()
