"""PD-I5-V1-SOURCE-FORMAT-RESILIENCE-PRODUCTION-01 — targeted format resilience suite.

Offline fixtures only (no live network). Covers classification, adapters, drift,
security bounds, and transition fail-closed behavior.
"""
from __future__ import annotations

import io
import zipfile
from typing import Callable

import pytest

from backend.app.schemas.i5_adapters import FetchEnvelope, SourceGovernanceSnapshot
from backend.app.services.i5 import conceptual_extraction as extract
from backend.app.services.i5.adapters.base import (
    AdapterFrameworkError,
    FixtureTransportResponse,
    default_registry,
    sha256_hex,
)
from backend.app.services.i5.adapters.format_drift import (
    classify_format_drift,
    structure_fingerprint_for_representation,
)
from backend.app.services.i5.adapters.pdf_jats import extract_jats_xml, extract_pdf_text
from backend.app.services.i5.adapters.representation_classifier import classify_representation
from backend.app.services.i5.adapters.tabular_docx import extract_csv_tsv_text, extract_docx_text
from backend.app.services.i5.know01.format_capability_matrix import (
    assert_v1_required_formats_covered,
    select_adapter_mode,
)


def _ok_gov(**overrides) -> SourceGovernanceSnapshot:
    base = dict(
        source_profile_id=1,
        registry_state="ACTIVE",
        runtime_eligibility="ELIGIBLE",
        rights_terms_state="ACCEPTABLE",
        robots_access_state="ALLOWED",
        rate_limit_policy="DEFINED",
        allowed_domain="example.org",
    )
    base.update(overrides)
    return SourceGovernanceSnapshot(**base)


def _transport(
    body: bytes,
    content_type: str,
    status: int = 200,
) -> Callable[[str], FixtureTransportResponse]:
    def _inner(url: str) -> FixtureTransportResponse:
        return FixtureTransportResponse(
            status_code=status,
            body=body,
            content_type=content_type,
            final_url=url,
        )

    return _inner


def _envelope(*, body: bytes, content_type: str, adapter_id: str = "i5.test", mode_hint: str = "") -> FetchEnvelope:
    return FetchEnvelope(
        request_id="r1",
        adapter_id=adapter_id,
        adapter_version="fmt-resilience-v1",
        canonical_url="https://example.org/doc",
        http_status=200,
        final_url="https://example.org/doc",
        retrieved_at=__import__("datetime").datetime.now(__import__("datetime").timezone.utc).replace(tzinfo=None),
        content_type=content_type,
        charset="utf-8",
        byte_count=len(body),
        content_hash=sha256_hex(body),
        etag=None,
        last_modified=None,
        disposition="OK",
        retryable=False,
        error_category=None,
        body=body,
    )


def _minimal_docx(text: str = "Governed DOCX health guidance text sample.") -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
  <Default Extension="xml" ContentType="application/xml"/>
  <Override PartName="/word/document.xml"
    ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
</Types>""",
        )
        zf.writestr(
            "word/document.xml",
            f"""<?xml version="1.0"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body><w:p><w:r><w:t>{text}</w:t></w:r></w:p></w:body>
</w:document>""",
        )
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Positive fixtures
# ---------------------------------------------------------------------------


def test_positive_html_json_rss_atom_jats_pdf_csv_tsv_docx():
    html = b"<html><title>T</title><body><p>Enough visible medical guidance text for extraction threshold.</p></body></html>"
    assert classify_representation(content_type="text/html", payload=html).representation == "HTML"
    cands = extract.extract_from_html(_envelope(body=html, content_type="text/html"))
    assert cands and cands[0].content_hash

    js = b'{"title":"API","text":"Enough JSON medical guidance text for extraction."}'
    assert classify_representation(content_type="application/json", payload=js).representation == "JSON"
    assert extract.extract_from_json_api(_envelope(body=js, content_type="application/json"))

    rss = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <item><title>A</title><description>Enough RSS medical guidance text here.</description>
      <link>https://example.org/a</link></item></channel></rss>"""
    assert classify_representation(content_type="application/rss+xml", payload=rss).representation == "RSS_ATOM"
    assert extract.extract_from_rss(_envelope(body=rss, content_type="application/rss+xml"))

    atom = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
      <entry><title>E</title><summary>Enough Atom medical guidance text here.</summary>
      <link href="https://example.org/e"/></entry></feed>"""
    assert classify_representation(content_type="application/atom+xml", payload=atom).representation == "RSS_ATOM"

    jats = b"""<?xml version="1.0"?><article><body><p>Enough JATS scientific article text for extract.</p></body></article>"""
    assert classify_representation(content_type="application/xml", payload=jats).representation in {
        "XML_JATS",
        "RSS_ATOM",
    }
    assert "JATS" in extract_jats_xml(jats) or "scientific" in extract_jats_xml(jats)

    pdf = b"%SEDI_PDF_TEXT_FIXTURE%\nEnough PDF medical guidance text for extraction."
    assert extract_pdf_text(pdf).startswith("Enough PDF")
    assert classify_representation(payload=b"%PDF-1.4 fake").representation == "PDF_TEXT"

    csv_body = b"topic,advice\nsleep,Enough CSV medical guidance text\n"
    assert extract_csv_tsv_text(csv_body)
    assert classify_representation(content_type="text/csv", payload=csv_body).representation == "CSV_TSV"

    tsv_body = b"topic\tadvice\nsleep\tEnough TSV medical guidance text\n"
    assert extract_csv_tsv_text(tsv_body, delimiter="\t")

    docx = _minimal_docx()
    assert "Governed DOCX" in extract_docx_text(docx)
    assert classify_representation(payload=docx, filename_hint="x.docx").representation == "DOCX"

    reg = default_registry()
    assert set(reg.list_ids()) >= {
        "i5.public_web_fetch",
        "i5.official_api",
        "i5.rss_feed",
        "i5.pdf_text",
        "i5.jats_xml",
        "i5.csv_tsv",
        "i5.docx",
    }
    assert_v1_required_formats_covered()


# ---------------------------------------------------------------------------
# Negatives / security
# ---------------------------------------------------------------------------


def test_negative_mime_spoof_invalid_pdf_xxe_zip_bomb_csv_unknown():
    # Fake Content-Type HTML but PDF signature
    with pytest.raises(AdapterFrameworkError, match="INVALID_CONTENT_TYPE"):
        classify_representation(content_type="text/html", payload=b"%PDF-1.7 binary")

    with pytest.raises(AdapterFrameworkError, match="REVIEW_REQUIRED|PDF_IMAGE_ONLY"):
        extract_pdf_text(b"%SEDI_PDF_IMAGE_ONLY_FIXTURE%")

    with pytest.raises(AdapterFrameworkError, match="PARSING_FAILED|INVALID"):
        extract_pdf_text(b"NOT_A_PDF")

    with pytest.raises(AdapterFrameworkError, match="PARSING_FAILED"):
        extract.extract_from_json_api(
            _envelope(body=b"{not-json", content_type="application/json")
        )

    xxe = b'<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><article>&xxe;</article>'
    with pytest.raises(AdapterFrameworkError, match="XML_ENTITY_FORBIDDEN|PARSING_FAILED"):
        extract_jats_xml(xxe)

    # Expansion heuristic
    bomb = b"<article>" + (b"&a;" * 60_000) + b"</article>"
    with pytest.raises(AdapterFrameworkError, match="CONTENT_TOO_LARGE|PARSING_FAILED"):
        extract_jats_xml(bomb)

    with pytest.raises(AdapterFrameworkError, match="BAD_DOCX|NOT_ZIP|PARSING_FAILED"):
        extract_docx_text(b"PK\x03\x04not-a-real-zip")

    # Nested archive rejected
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("[Content_Types].xml", "<Types/>")
        zf.writestr("word/document.xml", "<w:document xmlns:w='http://a'><w:t>x</w:t></w:document>")
        zf.writestr("word/embed.docx", b"PK nested")
    with pytest.raises(AdapterFrameworkError, match="NESTED_ARCHIVE|DOCX"):
        extract_docx_text(buf.getvalue())

    huge_field = b"a," + (b"x" * 5000)
    with pytest.raises(AdapterFrameworkError, match="CONTENT_TOO_LARGE"):
        extract_csv_tsv_text(huge_field)

    with pytest.raises(AdapterFrameworkError, match="UNSUPPORTED_FORMAT"):
        classify_representation(payload=b"\x00\x01\x02\xff\xfe binary blob")

    with pytest.raises(AdapterFrameworkError, match="UNSAFE_URL|scheme"):
        from backend.app.services.i5.adapters.base import assert_safe_public_https_url

        assert_safe_public_https_url("http://example.org/x")


def test_scanned_pdf_fail_closed_no_ocr():
    with pytest.raises(AdapterFrameworkError) as ei:
        extract_pdf_text(b"%SEDI_PDF_IMAGE_ONLY_FIXTURE%")
    assert "REVIEW_REQUIRED" in str(ei.value)
    assert "PDF_IMAGE_ONLY" in str(ei.value)


# ---------------------------------------------------------------------------
# Drift / transitions / identity
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "prev,cur,expected",
    [
        ("HTML", "PDF_TEXT", "FORMAT_CHANGED_SUPPORTED"),
        ("HTML", "JSON", "FORMAT_CHANGED_SUPPORTED"),
        ("RSS_ATOM", "HTML", "FORMAT_CHANGED_SUPPORTED"),
        ("XML_JATS", "PDF_TEXT", "FORMAT_CHANGED_SUPPORTED"),
        ("HTML", "PDF_IMAGE_ONLY", "FORMAT_CHANGED_UNSUPPORTED"),
        ("HTML", "UNKNOWN", "FORMAT_CHANGED_UNSUPPORTED"),
        ("HTML", "HTML", "SAME_SUPPORTED_FORMAT"),
    ],
)
def test_format_transitions(prev, cur, expected):
    d = classify_format_drift(
        source_identity_key="src:nhs_uk_live_well",
        previous_representation=prev,
        current_representation=cur,
    )
    assert d.classification == expected
    assert d.same_source_identity is True
    assert d.preserve_last_known_good is True
    if expected == "FORMAT_CHANGED_UNSUPPORTED":
        assert d.fail_closed is True
        assert d.publish_new_evidence is False
    if expected == "FORMAT_CHANGED_SUPPORTED":
        assert d.rights_recheck_required is True
        assert d.extraction_canary_required is True


def test_structure_drift_and_unreachable():
    body1 = b"<html><div><p>one</p></div></html>"
    body2 = b"<html><article><section><h1>two</h1></section></article></html>"
    fp1 = structure_fingerprint_for_representation("HTML", body1)
    fp2 = structure_fingerprint_for_representation("HTML", body2)
    d = classify_format_drift(
        source_identity_key="src:x",
        previous_representation="HTML",
        current_representation="HTML",
        previous_structure_fingerprint=fp1,
        current_structure_fingerprint=fp2,
    )
    assert d.classification == "STRUCTURE_DRIFT"
    u = classify_format_drift(
        source_identity_key="src:x",
        previous_representation="HTML",
        current_representation="HTML",
        unreachable=True,
    )
    assert u.classification == "UNREACHABLE"
    assert u.preserve_last_known_good is True


def test_adapter_fetch_fixture_csv_docx_and_no_duplicate_hash():
    reg = default_registry()
    gov = _ok_gov()
    csv_body = b"a,b\nEnough csv medical guidance,row\n"
    env1 = reg.get("i5.csv_tsv").fetch_fixture(
        request_id="1",
        url="https://example.org/data.csv",
        transport=_transport(csv_body, "text/csv"),
        governance=gov,
    )
    env2 = reg.get("i5.csv_tsv").fetch_fixture(
        request_id="2",
        url="https://example.org/data.csv",
        transport=_transport(csv_body, "text/csv"),
        governance=gov,
    )
    assert env1.content_hash == env2.content_hash
    assert env1.adapter_id == "i5.csv_tsv"
    assert env1.adapter_version

    docx = _minimal_docx()
    envd = reg.get("i5.docx").fetch_fixture(
        request_id="3",
        url="https://example.org/a.docx",
        transport=_transport(
            docx,
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ),
        governance=gov,
    )
    assert envd.adapter_id == "i5.docx"
    cands = extract.extract_candidates(envd, mode="DOCX")
    assert len(cands) == 1
    assert "DOCX" in cands[0].warnings or "docx" in cands[0].warnings[1]


def test_routing_modes_for_new_formats():
    assert select_adapter_mode(content_type="text/csv", payload_prefix=b"a,b\n") == "CSV_TSV"
    assert select_adapter_mode(filename_hint="note.docx", payload_prefix=_minimal_docx()) == "DOCX"
    assert select_adapter_mode(content_type="application/json", filename_hint="paper.pdf") == "OFFICIAL_API"
