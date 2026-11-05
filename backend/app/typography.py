"""R-064: ONE deterministic typography normalizer for everything Sedi writes (model replies, catalog texts, openers).

Leaf module (no project imports). Pure functions, idempotent: ``normalize(normalize(x)) == normalize(x)``.

What it guarantees
- paragraphs are separated by ONE blank line; each paragraph starts with a clean sentence (no bullet / markdown /
  stray punctuation) and, when it is a real sentence, ends with terminal punctuation; titles carry no trailing full stop;
- Persian / Arabic: «،» «؛» «؟» instead of Latin «, ; ?» next to Persian/Arabic text, no space before punctuation and one
  space after, one ellipsis character «…», guillemets «» around quoted Persian text, half-space (ZWNJ) in «می‌/نمی‌» and the
  plural «ها», Persian yeh / kaf in Persian, Persian (fa) or Arabic-Indic (ar) digits;
- English: no space before punctuation, one space after, a capital letter at a paragraph start, one «…»;
- it never touches ``{placeholders}``, URLs, e-mail addresses, times («10:30») or decimals («3.5»).
"""

from __future__ import annotations

import re
from typing import Final

ZWNJ: Final[str] = "‌"
_AR: Final[str] = "؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿"
_DIGITS_RTL: Final[str] = "۰-۹٠-٩"
# Persian / Arabic LETTERS only (no digits): a full stop or colon between digits is a decimal point or a clock.
_ARL: Final[str] = "ء-يٱ-ۓۺ-ۿݐ-ݿﭐ-﷿ﹰ-﻿"
_LATIN_DIGITS: Final[str] = "0123456789"
_PERSIAN_DIGITS: Final[str] = "۰۱۲۳۴۵۶۷۸۹"
_ARABIC_DIGITS: Final[str] = "٠١٢٣٤٥٦٧٨٩"

_TERMINAL: Final[str] = ".!?؟…:"
_CLOSERS: Final[str] = "»)\"'”]"

_PLACEHOLDER = re.compile(r"\{[^{}]*\}")
_LEADING_JUNK = re.compile(r"^[\s\-–—•*·.:،؛]+")
_BULLET = re.compile(r"^\s*(?:[-*•·]|#{1,6})\s+")
_PROTECT = re.compile(r"\{[^{}]*\}|https?://\S+|www\.\S+|\S+@\S+\.\S+")


def _rtl(lang: str) -> bool:
    return (lang or "").split("-")[0].lower() in ("fa", "ar")


def _protect(text: str) -> tuple[str, list[str]]:
    """Swap placeholders / URLs / e-mails for opaque tokens so no rule can touch them."""
    saved: list[str] = []

    def keep(match: re.Match) -> str:
        saved.append(match.group(0))
        return "" + chr(0xE100 + len(saved) - 1) + ""

    return _PROTECT.sub(keep, text), saved


def _restore(text: str, saved: list[str]) -> str:
    for index, original in enumerate(saved):
        text = text.replace("" + chr(0xE100 + index) + "", original)
    return text


def _digits(token: str, lang: str) -> str:
    if re.search(r"[A-Za-z]", token):
        return token
    if lang == "fa":
        table = str.maketrans(_LATIN_DIGITS + _ARABIC_DIGITS, _PERSIAN_DIGITS * 2)
    elif lang == "ar":
        table = str.maketrans(_LATIN_DIGITS + _PERSIAN_DIGITS, _ARABIC_DIGITS * 2)
    else:
        return token
    return token.translate(table)


def _chars_rtl(text: str, lang: str, digits: bool) -> str:
    if lang == "fa":
        text = text.replace("ي", "ی").replace("ك", "ک").replace("ى", "ی")
    if digits:
        text = " ".join(_digits(token, lang) for token in text.split(" "))
    text = re.sub(r"\.{3,}|…+", "…", text)
    # Latin marks become Persian/Arabic marks when they follow Persian/Arabic text (decimals and times are untouched).
    after_rtl = "(?<=[" + _AR + _DIGITS_RTL + r"»)…])"
    text = re.sub(after_rtl + r"\s*,(?![0-9" + _DIGITS_RTL + "])", "،", text)
    text = re.sub(after_rtl + r"\s*;", "؛", text)
    text = re.sub(after_rtl + r"\s*\?", "؟", text)
    # straight / curly double quotes around Persian text become guillemets
    text = re.sub(r"[\"“]([^\"“”\n]*[" + _AR + r"][^\"“”\n]*)[\"”]", "«\\1»", text)
    text = re.sub(r"«\s+", "«", text)
    text = re.sub(r"\s+»", "»", text)
    # no space before closing marks, one after
    text = re.sub(r"[ \t]+([،؛؟.!:…)\]])", r"\1", text)
    text = re.sub(r"([(\[])[ \t]+", r"\1", text)
    text = re.sub(r"([،؛؟!])(?=[" + _ARL + r"«(])", r"\1 ", text)
    text = re.sub(r"([.:…])(?=[" + _ARL + r"«])", r"\1 ", text)
    if lang == "fa":
        text = re.sub(r"(?<![" + _AR + r"])(ن?می) (?=[" + _AR + "])", "\\1" + ZWNJ, text)
        text = re.sub(
            r"([" + _AR + r"]) (ها|های|هایی|هایم|هایت|هایش)(?![" + _AR + "])",
            "\\1" + ZWNJ + "\\2",
            text,
        )
    return text


def _chars_en(text: str) -> str:
    text = re.sub(r"\.{3,}|…+", "…", text)
    text = re.sub(r"[ \t]+([,.;:!?…)\]])", r"\1", text)
    text = re.sub(r"([(\[])[ \t]+", r"\1", text)
    text = re.sub(r"([,;!?])(?=[A-Za-z])", r"\1 ", text)
    text = re.sub(r"(?<=[a-z])([.:])(?=[A-Z][a-z])", r"\1 ", text)
    return text


def _chars(text: str, lang: str, digits: bool) -> str:
    text, saved = _protect(text)
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\t", " ").replace(" ", " ")
    text = re.sub(r"(\*\*|__)", "", text)
    text = _chars_rtl(text, lang, digits) if _rtl(lang) else _chars_en(text)
    text = re.sub(r"[ ]{2,}", " ", text)
    text = "\n".join(line.strip(" ") for line in text.split("\n"))
    return _restore(text, saved)


def _end_paragraph(paragraph: str, lang: str) -> str:
    """A real sentence (5+ words) that stops without punctuation gets its full stop; headings stay as they are."""
    body = paragraph.rstrip()
    core = body.rstrip(_CLOSERS)
    if not core or core[-1] in _TERMINAL + "،؛؟…":
        return body
    if len(re.findall(r"\S+", core)) < 4:
        return body
    return core + "." + body[len(core):]


def _start_paragraph(paragraph: str, lang: str) -> str:
    cleaned = _BULLET.sub("", paragraph)
    cleaned = _LEADING_JUNK.sub("", cleaned) if not cleaned.startswith("") else cleaned
    if lang == "en" and cleaned[:1].islower():
        cleaned = cleaned[:1].upper() + cleaned[1:]
    return cleaned


def normalize(text: str, lang: str = "fa", *, paragraphs: bool = True, digits: bool = True) -> str:
    """Normalize a chat text / opener / catalog text. ``paragraphs=False`` keeps the existing line breaks and only cleans
    characters (notification bodies); ``digits=False`` keeps the digits as written (catalog texts)."""
    if not text or not str(text).strip():
        return (text or "").strip() if isinstance(text, str) else ""
    lang = (lang or "fa").split("-")[0].lower()
    cleaned = _chars(str(text), lang, digits)
    if not paragraphs:
        return re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    parts = [p.strip() for p in re.split(r"\n+", cleaned) if p.strip()]
    out = []
    for part in parts:
        part = _start_paragraph(part, lang)
        if part:
            out.append(_end_paragraph(part, lang))
    return "\n\n".join(out)


def normalize_title(text: str, lang: str = "fa") -> str:
    """A heading / notification title: one line, clean characters, no trailing full stop."""
    one_line = " ".join(str(text or "").split())
    cleaned = _chars(one_line, (lang or "fa").split("-")[0].lower(), False).strip()
    cleaned = _BULLET.sub("", cleaned)
    return cleaned.rstrip(".،؛,;: ").strip()
