from backend.app.services.intelligence.plain_text import to_plain_chat_text


def test_strips_markdown_emphasis_headings_and_star_bullets():
    src = "جواد، **ALS** یا «اسکلروز»\n## علائم\n* ضعف\n* گرفتگی\nیک `کد` و __تأکید__"
    out = to_plain_chat_text(src)
    assert "**" not in out and "__" not in out and "`" not in out and "##" not in out
    assert "ALS" in out and "- ضعف" in out and "علائم" in out and "تأکید" in out


def test_plain_text_and_empty_unchanged():
    assert to_plain_chat_text("سلام، حالت چطوره؟") == "سلام، حالت چطوره؟"
    assert to_plain_chat_text("") == ""
