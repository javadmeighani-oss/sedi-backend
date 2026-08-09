"""CAP25 federated SBMU hospital acquisition + CAP24 still blocked."""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from backend.app.services.i5.iran_directory_federation import (
    SBMU_HOSPITAL_SEED,
    parse_sbmu_affiliated_facilities,
    acquire_sbmu_affiliated_hospitals,
)
from backend.app.services.i5.iran_directory_import import apply_plan, dry_run_plan
from backend.app.services.i5.iran_directory_source_manifest import (
    SBMU_FED_HOSPITAL_SOURCE,
    get_authorized_source,
    SourceNotAuthorizedError,
)
from backend.app.services.i5.source_governance_decisions import (
    DIRECT_PUBLISHER_PERMISSION_IS_NOT_A_UNIVERSAL_PREREQUISITE,
    PUBLIC_WEB_INTERNAL_FACT_EVIDENCE_DISTILLATION,
    FEDERATED_OFFICIAL_PROVIDER_WEB_SOURCE,
    evaluate_source_admissibility,
)


_FAKE_PAGE = (
    "تور دانشگاه 21 بیمارستان مراکز پزشکی، آموزشی "
    "اختر امام حسین (ع) آیت الله طالقانی دکتر مسیح دانشوری شهدای تجریش "
    "شهید لبافی نژاد شهید مدرس طرفه لقمان حکیم مفید مهدیه پانزده خرداد "
    "مراکز درمانی امام خمینی (ره) فیروزکوه انصار الغدیر حضرت فاطمه (س) دماوند "
    "سوم شعبان دماوند شهدای پاکدشت شهدای گمنام شهید ستاری قرچک زعیم پاکدشت مفتح ورامین"
)


def test_permanent_governance_decisions_ratified():
    assert DIRECT_PUBLISHER_PERMISSION_IS_NOT_A_UNIVERSAL_PREREQUISITE is True
    assert PUBLIC_WEB_INTERNAL_FACT_EVIDENCE_DISTILLATION == "ALLOWED_WITH_GOVERNANCE"
    assert FEDERATED_OFFICIAL_PROVIDER_WEB_SOURCE == "ALLOWED_WITH_GOVERNANCE"


def test_parse_sbmu_requires_live_name_presence():
    records, rejected = parse_sbmu_affiliated_facilities(_FAKE_PAGE)
    assert len(records) == len(SBMU_HOSPITAL_SEED)
    assert rejected == []
    assert all(r["source_system_label"] == SBMU_FED_HOSPITAL_SOURCE for r in records)
    assert all(r["facility_type"] in {"HOSPITAL", "MEDICAL_CENTER"} for r in records)
    missing_page = "صفحه بدون نام بیمارستان"
    records2, rejected2 = parse_sbmu_affiliated_facilities(missing_page)
    assert records2 == []
    assert len(rejected2) == len(SBMU_HOSPITAL_SEED)


def test_acquire_sbmu_host_lock_and_http(monkeypatch):
    def _get(url, **kwargs):
        return SimpleNamespace(status_code=200, content=_FAKE_PAGE.encode("utf-8"), url=url)

    result = acquire_sbmu_affiliated_hospitals(http_get=_get)
    assert result.status_code == 200
    assert len(result.records) == len(SBMU_HOSPITAL_SEED)
    assert result.coverage_class == "OFFICIAL_FEDERATED_SEED"

    def _evil(url, **kwargs):
        return SimpleNamespace(
            status_code=200,
            content=_FAKE_PAGE.encode("utf-8"),
            url="https://evil.example/page",
        )

    with pytest.raises(ValueError, match="FEDERATION_HOST_MISMATCH"):
        acquire_sbmu_affiliated_hospitals(http_get=_evil)


def test_cap25_federation_apply_and_replay(db):
    get_authorized_source(SBMU_FED_HOSPITAL_SOURCE)
    records, _ = parse_sbmu_affiliated_facilities(_FAKE_PAGE)
    plan1 = apply_plan(db, records)
    db.commit()
    assert plan1["hospital"]["insert"] == len(records)
    plan2 = apply_plan(db, records)
    db.commit()
    assert plan2["hospital"]["insert"] == 0
    after = dry_run_plan(records, db)
    assert after["hospital"]["insert"] == 0


def test_cap24_still_blocked_for_population():
    with pytest.raises(SourceNotAuthorizedError):
        get_authorized_source("iran_laboratory_official_pending")


def test_sbmu_source_admissibility_matrix():
    from backend.app.services.i5.iran_directory_source_manifest import SOURCE_MANIFEST

    row = SOURCE_MANIFEST[SBMU_FED_HOSPITAL_SOURCE]
    decision = evaluate_source_admissibility(row)
    assert decision["FINAL_ADMISSIBILITY"] is True
    assert decision["CRAWLER_ACCESS_ADMISSIBILITY"] is True
    assert decision["CONTENT_USE_ADMISSIBILITY"] is True
