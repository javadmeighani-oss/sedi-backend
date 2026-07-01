"""Gate 3G — semantic HTML parser and quality heuristics (Stage A3)."""

import os

os.environ["SMS_DISABLED"] = "true"

import pytest

from backend.app.services.gate3.content_parser import (
    HTML_MIN_TEXT_LENGTH,
    extract_semantic_html_text,
    is_hub_page_thin,
    is_nav_heavy,
    parse_content,
)
from backend.app.services.gate3.knowledge_ai_review_service import KnowledgeAIReviewService
from backend.app import models
from datetime import datetime


def _article_html(body: str) -> bytes:
    return f"""<!DOCTYPE html>
<html><head><title>Article Title</title></head>
<body>
<header><nav>Skip to main content Search Health A to Z</nav></header>
<main>
<article>{body}</article>
</main>
<footer>Support links Accessibility statement Cookies Crown copyright</footer>
</body></html>""".encode("utf-8")


def _nhs_hub_html() -> bytes:
    return b"""<!DOCTYPE html>
<html><head><title>Sleep and tiredness - NHS</title></head>
<body>
<header class="nhsuk-header"><nav>Skip to main content NHS Search the NHS website</nav></header>
<main class="nhsuk-main-wrapper" id="maincontent">
<h1>Sleep and tiredness</h1>
<p>Reasons why you might feel tired and advice about what you can do to prevent tiredness.</p>
<ul>
<li>Self-help tips to fight tiredness</li>
<li>Bedtime meditation video</li>
</ul>
</main>
<footer class="nhsuk-footer">Support links Health A to Z Our policies Cookies Crown copyright</footer>
</body></html>"""


def test_semantic_parser_extracts_article_excludes_nav_footer():
    body = (
        "Getting enough sleep helps your body recover and supports daily energy. "
        "Aim for a regular bedtime and reduce screen time before sleep. "
        "Keep your bedroom cool, dark, and quiet for better rest quality. "
        "Avoid caffeine late in the day and build a calming wind-down routine. "
        "If tiredness persists despite good habits, speak to a pharmacist or GP for advice. "
        "Most adults need between seven and nine hours of sleep each night for good health."
    )
    html = _article_html(body)
    parsed = parse_content(html, "text/html")
    assert parsed.parser_type == "html"
    assert parsed.extraction_container == "article"
    assert "regular bedtime" in parsed.text
    assert "Skip to main content" not in parsed.text
    assert "Crown copyright" not in parsed.text
    assert len(parsed.text) >= HTML_MIN_TEXT_LENGTH


def test_nhs_like_hub_page_rejected():
    with pytest.raises(ValueError, match="parse_hub_page_thin|parse_too_short"):
        parse_content(_nhs_hub_html(), "text/html")


def test_hub_detection_helpers():
    hub_text = (
        "Sleep and tiredness Reasons why you might feel tired. "
        "Self-help tips to fight tiredness Bedtime meditation video"
    )
    assert is_hub_page_thin(hub_text)
    assert not is_nav_heavy(hub_text)


def test_nav_heavy_full_page_text_rejected():
    nav_text = (
        "Skip to main content NHS Search the NHS website Search Health A to Z NHS services "
        "Healthy living Mental health Support links Accessibility statement Cookies Crown copyright "
    ) + ("Navigation link text " * 30)
    assert is_nav_heavy(nav_text)
    with pytest.raises(ValueError, match="parse_nav_heavy"):
        parse_content(
            f"<html><body><main><article>{nav_text}</article></main></body></html>".encode(),
            "text/html",
        )


def test_article_like_html_passes_minimum_quality():
    guidance = (
        "Self-help tips to fight tiredness include keeping a regular sleep schedule, "
        "reducing caffeine in the afternoon, taking short daytime walks, and drinking "
        "enough water during the day. Stress and worry can make you feel exhausted, so "
        "relaxation exercises may help. If you have felt tired for more than four weeks, "
        "see a GP to rule out common causes. Most adults need seven to nine hours of sleep. "
        "Avoid heavy meals and alcohol before bed, and keep screens out of the bedroom when possible."
    )
    parsed = parse_content(_article_html(guidance), "text/html")
    assert len(parsed.text) >= HTML_MIN_TEXT_LENGTH
    assert "regular sleep schedule" in parsed.text


def test_manual_plain_text_allows_low_min_length():
    short = "Curated admin note for KB seed."
    parsed = parse_content(short.encode("utf-8"), "text/plain", min_text_length=1)
    assert parsed.parser_type == "text"
    assert parsed.text == short


def test_no_useful_main_content_raises():
    with pytest.raises(ValueError, match="parse_no_useful_main_content"):
        parse_content(b"<html><body></body></html>", "text/html")


def test_extract_semantic_prefers_article_over_main():
    html = "<html><body><main>main text</main><article>article text wins</article></body></html>"
    text, container = extract_semantic_html_text(html)
    assert container == "article"
    assert "article text wins" in text


def test_ai_review_blocks_auto_approve_on_parser_quality_findings():
    now = datetime.utcnow()
    src = models.KnowledgeSource(
        slug="sleep-official",
        name="Sleep",
        category="sleep",
        trust_level="official",
        source_url="https://www.nhs.uk/live-well/sleep-and-tiredness/",
        locale="en",
        ingestion_status="draft",
        auto_approve_low_risk=True,
        review_required=False,
        created_at=now,
        updated_at=now,
    )
    thin_hub = (
        "Sleep and tiredness Reasons why you might feel tired. "
        "Self-help tips to fight tiredness Bedtime meditation video"
    )
    review = KnowledgeAIReviewService().review(
        src,
        thin_hub,
        parser_type="html",
        parser_findings=[{"code": "parse_hub_page_thin", "severity": "high"}],
    )
    assert review.auto_approve_allowed is False
    assert review.parse_quality_score <= 0.2
    assert any(f["code"] == "parse_hub_page_thin" for f in review.review_findings)
