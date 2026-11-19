"""J3-b (D-407): check what a search result CLAIMS against the page it came from, and read the facts the page really publishes.

The search model reports name / phone / address / visit days / rating. A model can mis-copy or invent them. This module reads the
public page (``safe_fetch``) and decides, field by field:

  phone     "verified"   the number's digits are on the page (shown as published, any landline or mobile the page itself publishes)
            "unchecked"  the page could not be read (blocked, JS-only, robots): shown only with a «not verified» label
            "rejected"   the page was read and the number is NOT on it: never shown
  address   kept only when most of its distinctive words are on the page
  days      only the weekday names that appear on the page next to a time / visit cue
  rating    Paziresh24: the page's own numbers; other sites: only a value + count that both appear on the page

Paziresh24 doctor pages are read with the existing structured parser (``iran_directory_p24``): the PAGE wins over the model for phone,
address and rating, and the page's own «next available turn» text is reported. Deterministic, never raises, no model call.
"""
from __future__ import annotations

import html as _html
import json
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, Optional

from backend.app.services.i5 import safe_fetch

_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩٫", "01234567890123456789.")
_FOLD = (("ي", "ی"), ("ى", "ی"), ("ك", "ک"), ("ة", "ه"))
_SCRIPT_STYLE = re.compile(r"<(script|style|noscript)\b[^>]*>.*?</\1>", re.S | re.I)
_TAGS = re.compile(r"<[^>]+>")
_PHONE_RUN = re.compile(r"[0-9۰-۹٠-٩][0-9۰-۹٠-٩\s\-–()+]{6,}[0-9۰-۹٠-٩]")
_FREETURN = re.compile(r'"freeturn_text"\s*:\s*"([^"]{3,60})"')

_DAYS = (
    ("شنبه", ("شنبه",)),
    ("یکشنبه", ("یکشنبه", "1شنبه")),
    ("دوشنبه", ("دوشنبه", "2شنبه")),
    ("سه‌شنبه", ("سهشنبه", "3شنبه")),
    ("چهارشنبه", ("چهارشنبه", "4شنبه")),
    ("پنجشنبه", ("پنجشنبه", "5شنبه")),
    ("جمعه", ("جمعه",)),
)
_TIME_CUE = re.compile(r"ساعت|ویزیت|نوبت|حضور|کاری|مطب|\d{1,2}\s*[:٫.]\s*\d{2}|am\b|pm\b", re.I)
_OPEN_24H = re.compile(r"شبانه[ ‌]?روزی|24 ?ساعته|24 ?hours?|24 ?/ ?7|round the clock", re.I)
_GENERIC_ADDRESS_WORDS = frozenset({"خیابان", "پلاک", "طبقه", "واحد", "ساختمان", "کوچه", "بلوار", "میدان", "تهران", "ایران", "نبش", "مجتمع", "برج"})


def _fold(text: str) -> str:
    out = (text or "").translate(_DIGITS).lower()
    for a, b in _FOLD:
        out = out.replace(a, b)
    return out


def _squash(text: str) -> str:
    return re.sub(r"[\s‌‏‎\-]+", "", _fold(text))


def visible_text(html: str) -> str:
    stripped = _SCRIPT_STYLE.sub(" ", html or "")
    return re.sub(r"\s+", " ", _html.unescape(_TAGS.sub(" ", stripped))).strip()


def page_digit_runs(raw: str) -> set[str]:
    """Every digit run on the page (phone-looking), digits only, in ASCII, from the visible text AND the embedded JSON. A run that is
    two numbers written next to each other is also split at wide gaps."""
    runs: set[str] = set()
    for m in _PHONE_RUN.finditer(_html.unescape(raw or "")):
        pieces = [m.group(0)] + [p for p in re.split(r"\s{2,}|[،,/]", m.group(0)) if p.strip()]
        for piece in pieces:
            digits = re.sub(r"\D", "", piece.translate(_DIGITS))
            if 8 <= len(digits) <= 30:
                runs.add(digits)
    return runs


def _claimed_digits(phone: Optional[str]) -> str:
    digits = re.sub(r"\D", "", str(phone or "").translate(_DIGITS))
    if digits.startswith("0098"):
        digits = digits[4:]
    elif digits.startswith("98") and len(digits) >= 11:
        digits = digits[2:]
    return digits.lstrip("0")


def _national(digits: str) -> str:
    """The number without the country code and the trunk 0: 0098 21 2279 2694 / +98 21... / 021... all -> 2122792694."""
    d = re.sub(r"\D", "", digits or "")
    if d.startswith("0098"):
        d = d[4:]
    elif d.startswith("98") and len(d) >= 11:
        d = d[2:]
    return d.lstrip("0")


def phone_on_page(phone: Optional[str], runs: set[str]) -> bool:
    """The COMPLETE number (area code included) is on the page - never a mere suffix match (Codex P2, PR 190). A digit run that is
    two numbers written next to each other is tolerated: the claimed number may be its first or its last part."""
    want = _national(_claimed_digits(phone))
    if len(want) < 8:
        return False
    for run in runs:
        got = _national(run)
        if got == want:
            return True
        if len(got) > len(want) and (got.startswith(want) or got.endswith(want)):
            rest = got[len(want):] if got.startswith(want) else got[: len(got) - len(want)]
            if len(rest) >= 8:
                return True
    return False


_NEGATION_AFTER = re.compile(r"^.{0,24}?(?:نیست|ندارد|ندارند|نمی ?باشد|نمیباشد|not|n't|no longer|closed)", re.I)
_NEGATION_BEFORE = re.compile(r"(?:^|[\s،,.])(?:غیر|نه|not|no|never|without|بدون)\s+(?:\w+\s+){0,2}$|(?:^|[\s،,.])(?:غیر|بدون)\s*$", re.I)


def _affirmative_24h(folded_text: str) -> bool:
    """«شبانه‌روزی» counts only when it is stated, not negated: «مطب شبانه‌روزی نیست» is the opposite (Codex P2, PR 190)."""
    for m in _OPEN_24H.finditer(folded_text):
        after = folded_text[m.end(): m.end() + 40]
        before = folded_text[max(0, m.start() - 14): m.start()]
        if _NEGATION_AFTER.search(after) or _NEGATION_BEFORE.search(before):
            continue
        return True
    return False


def published_phone(*values: Any) -> Optional[str]:
    """The first usable number AS PUBLISHED (a landline or a mobile the page itself shows); placeholders and fragments are dropped."""
    for value in values:
        for part in re.split(r"[,،/\n؛;]|(?<=\d)\s+(?=0)", str(value or "")):
            digits = re.sub(r"\D", "", part.translate(_DIGITS))
            if len(digits) < 8 or "0000000" in digits or len(set(digits)) < 3:
                continue
            if len(digits) > 12:
                continue
            return digits if digits.startswith(("0", "+")) else ("0" + digits if len(digits) == 10 else digits)
    return None


def address_on_page(address: Optional[str], page_text: str) -> bool:
    if not address:
        return False
    page = _squash(page_text)
    tokens = [t for t in re.split(r"[\s\-،,.؛:/]+", _fold(address).replace("‌", " ")) if len(t) >= 3 and t not in _GENERIC_ADDRESS_WORDS]
    tokens = [t for t in tokens if not t.isdigit() or len(t) >= 3]
    if len(tokens) < 2:
        return False
    hits = sum(1 for t in tokens if _squash(t) in page)
    return hits >= max(2, round(0.6 * len(tokens)))


_DAY_ORDER = (
    ("چهارشنبه", ("چهارشنبه", "4شنبه")), ("پنجشنبه", ("پنجشنبه", "5شنبه")), ("سه‌شنبه", ("سهشنبه", "3شنبه")),
    ("یکشنبه", ("یکشنبه", "1شنبه")), ("دوشنبه", ("دوشنبه", "2شنبه")), ("جمعه", ("جمعه",)), ("شنبه", ("شنبه",)),
)  # LONGEST names first: «یکشنبه» must not also count as «شنبه»


def _day_positions(squashed: str) -> dict[str, list[int]]:
    masked, out = squashed, {}
    for canon, variants in _DAY_ORDER:
        out[canon] = []
        for v in variants:
            start = 0
            while True:
                pos = masked.find(v, start)
                if pos < 0:
                    break
                out[canon].append(pos)
                masked = masked[:pos] + "#" * len(v) + masked[pos + len(v):]
                start = pos + len(v)
    return out


def days_on_page(days: Any, page_text: str) -> tuple[str, ...]:
    """The claimed weekday names that the page itself shows near a time / visit cue (canonical names, week order)."""
    claimed = [days] if isinstance(days, str) else list(days or [])
    claim_pos = _day_positions(_squash(" ".join(str(d) for d in claimed if d)))
    wanted = {canon for canon, pos in claim_pos.items() if pos}
    if not wanted:
        return ()
    squashed, idx = _squash_with_map(_fold(page_text))
    page = _fold(page_text)
    found = _day_positions(squashed)
    out: list[str] = []
    for canon, _variants in _DAYS:
        if canon not in wanted:
            continue
        for pos in found.get(canon, []):
            a = idx[pos]
            if _TIME_CUE.search(page[max(0, a - 90): a + 90]):
                out.append(canon)
                break
    return tuple(out)


def _squash_with_map(text: str) -> tuple[str, list[int]]:
    chars, idx = [], []
    for i, ch in enumerate(text):
        if not re.match(r"[\s‌‏‎\-]", ch):
            chars.append(ch)
            idx.append(i)
    return "".join(chars), idx


@dataclass(frozen=True)
class Verification:
    read: bool = False
    reason: str = ""
    phone: Optional[str] = None
    phone_status: str = "none"  # verified | unchecked | rejected | none
    address: Optional[str] = None
    address_verified: bool = False
    visit_days: tuple = ()
    next_turn: Optional[str] = None
    rating_avg: Optional[float] = None
    rating_count: Optional[int] = None
    checked_on: Optional[str] = None
    open_24h: bool = False


def _p24(raw: bytes) -> dict[str, Any]:
    try:
        from backend.app.services.i5 import iran_directory_p24 as p24

        doc, centers = p24.parse_doctor_page(raw)
        if not doc:
            return {}
        out = {"phone": doc.get("phone"), "address": doc.get("address"), "rating_avg": doc.get("rating_avg"),
               "rating_count": doc.get("rating_count")}
        for c in centers or []:  # the doctor's own physical center when the doctor record has no number
            out["phone"] = out["phone"] or c.get("phone")
            out["address"] = out["address"] or c.get("address")
        return out
    except Exception:  # noqa: BLE001
        return {}


_RATING_CUE = re.compile(r"امتیاز|رضایت|نمره|ستاره|rating|rated|stars?|score|of 5|out of 5|از 5|/ ?5", re.I)
_COUNT_CUE = re.compile(r"نظر|رای|رأی|بازخورد|بیمار|دیدگاه|review|rating|vote|feedback|patients?", re.I)


def _rating_evidence(text: str, avg: float, count: str) -> bool:
    """The score and the review count must each stand NEXT TO rating words on the page; unrelated digits («512 Main St») are not
    evidence (Codex P2, PR 190)."""
    t = _fold(text).replace("\u066b", ".").replace(",", ".")
    avg_s = f"{avg:g}"
    score_ok = any(_RATING_CUE.search(t[max(0, m.start() - 40): m.end() + 40])
                   for m in re.finditer(r"(?<![\d.])" + re.escape(avg_s) + r"(?![\d])", t))
    count_ok = any(_COUNT_CUE.search(t[max(0, m.start() - 40): m.end() + 40])
                   for m in re.finditer(r"(?<![\d.])" + re.escape(count) + r"(?![\d])", t))
    return score_ok and count_ok


def _num(value: Any) -> Optional[float]:
    try:
        v = float(str(value).translate(_DIGITS).replace(",", "."))
        return v if 0 < v <= 5.0 else None
    except (TypeError, ValueError):
        return None


def verify_result(item: dict[str, Any], *, fetch: Optional[Callable[[str], "safe_fetch.FetchResult"]] = None,
                  today: Optional[date] = None) -> Verification:
    """Compare one search result with its page. Never raises."""
    claimed_phone = published_phone(item.get("phone"))
    claimed_address = " ".join(str(item.get("address") or "").split()) or None
    today_s = (today or date.today()).isoformat()
    try:
        fr = (fetch or safe_fetch.fetch_page)(str(item.get("source_url") or ""))
        if not fr.ok:
            return Verification(read=False, reason=fr.reason, phone=claimed_phone, phone_status="unchecked" if claimed_phone else "none",
                                address=claimed_address, checked_on=None)
        raw = fr.body.decode("utf-8", "replace")
        text = visible_text(raw)
        runs = page_digit_runs(raw)
        host = (str(fr.url).split("/")[2] if "//" in str(fr.url) else "").lower()
        truth = _p24(fr.body) if host.endswith("paziresh24.com") else {}
        # --- phone
        page_phone = published_phone(truth.get("phone")) if truth else None
        if page_phone:
            phone, status = page_phone, "verified"
        elif claimed_phone and phone_on_page(claimed_phone, runs):
            phone, status = claimed_phone, "verified"
        elif claimed_phone:
            phone, status = None, "rejected"
        else:
            phone, status = None, "none"
        # --- address
        t_addr = " ".join(str(truth.get("address") or "").split()) or None
        if t_addr:
            address, addr_ok = t_addr, True
        elif claimed_address and address_on_page(claimed_address, text):
            address, addr_ok = claimed_address, True
        else:
            address, addr_ok = None, False
        # --- days / next turn
        days = days_on_page(item.get("visit_days"), text)
        m = _FREETURN.search(raw)
        next_turn = " ".join(m.group(1).split()) if m else None
        # --- rating
        r_avg, r_cnt = _num(truth.get("rating_avg")), None
        if truth:
            r_cnt = int(truth["rating_count"]) if str(truth.get("rating_count") or "").isdigit() else None
        else:
            claimed_avg = _num(item.get("rating"))
            claimed_cnt = str(item.get("rating_count") or "").translate(_DIGITS).strip()
            if claimed_avg and claimed_cnt.isdigit() and _rating_evidence(text, claimed_avg, claimed_cnt):
                r_avg, r_cnt = claimed_avg, int(claimed_cnt)
        if r_avg is None:
            r_cnt = None
        open24 = _affirmative_24h(_fold(text))
        return Verification(read=True, open_24h=open24, phone=phone, phone_status=status, address=address, address_verified=addr_ok,
                            visit_days=days, next_turn=next_turn, rating_avg=r_avg, rating_count=r_cnt, checked_on=today_s)
    except Exception as exc:  # noqa: BLE001
        return Verification(read=False, reason=type(exc).__name__, phone=claimed_phone,
                            phone_status="unchecked" if claimed_phone else "none", address=claimed_address)
