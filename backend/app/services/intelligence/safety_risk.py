"""Section 15-I4 — Deterministic chat safety / risk engine (no DB/LLM/network).

Fix1: per-match informational/denial exclusions (no global suppress), material
legacy emergency/high parity under single I4 authority, fail-closed seams.
Fix2: intra-word apostrophe fold; conceptual self-harm definition exclusions;
Persian current-intent self-harm phrases.
Fix3: Persian past-tense self-harm denial phrases (overlap-only suppression).
Message text is request-local only. Results expose enums/rule IDs only.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Optional, Sequence

from backend.app.services.intelligence.contracts import (
    LanguageCode,
    PostGenerationSafetyResult,
    PostGenerationSafetyStatus,
    RiskAssessment,
    RiskDomain,
    RiskLevel,
    SafetyAction,
    SafetyConstraints,
    SafetyResponse,
)

REGISTRY_VERSION = "sedi.safety.risk.v1"

_AR_FA_TRANSLATION = str.maketrans(
    {
        "ك": "ک",
        "ي": "ی",
        "ى": "ی",
        "ة": "ه",
        "ؤ": "و",
        "أ": "ا",
        "إ": "ا",
        "آ": "ا",
        "ٔ": "",
        "ٕ": "",
        "َ": "",
        "ُ": "",
        "ِ": "",
        "ّ": "",
        "ْ": "",
        "ً": "",
        "ٌ": "",
        "ٍ": "",
    }
)

# Apostrophe / quotation variants (ASCII + common Unicode; NFKC may already fold some).
_APOSTROPHE_CHARS = frozenset(
    {
        "'",  # ASCII APOSTROPHE
        "\u2019",  # RIGHT SINGLE QUOTATION MARK ’
        "\u2018",  # LEFT SINGLE QUOTATION MARK ‘
        "\u02bc",  # MODIFIER LETTER APOSTROPHE ʼ
        "\u02b9",  # MODIFIER LETTER PRIME
        "\uff07",  # FULLWIDTH APOSTROPHE
    }
)

# Intra-word apostrophe: remove so can't→cant, don't→dont (before punctuation→space).
_INTRA_WORD_APOSTROPHE_RE = re.compile(
    r"(?<=\w)['\u2018\u2019\u02bc\u02b9\uff07](?=\w)"
)


def normalize_safety_text(raw: str) -> str:
    """Request-local Unicode normalization for safety matching only.

    Fix2: fold intra-word apostrophes to empty before treating remaining
    punctuation as separators, so contractions match apostrophe-free registry
    phrases while quoted boundaries stay separators.
    """
    text = unicodedata.normalize("NFKC", raw or "")
    text = text.translate(_AR_FA_TRANSLATION)
    text = text.replace("\u200c", "").replace("\u200d", "")
    text = text.casefold()
    # Canonical contraction fold (can't → cant, don't → dont, I'm → im).
    text = _INTRA_WORD_APOSTROPHE_RE.sub("", text)
    out: list[str] = []
    for ch in text:
        if ch.isalnum() or ch.isspace():
            out.append(ch)
        elif ch in _APOSTROPHE_CHARS:
            # Standalone quote at word boundary → separator (do not glue tokens).
            out.append(" ")
        else:
            out.append(" ")
    return re.sub(r"\s+", " ", "".join(out)).strip()


def _phrase_spans(normalized: str, phrase: str) -> list[tuple[int, int]]:
    """Return [start, end) spans of phrase in normalized text (boundary-safe)."""
    needle = normalize_safety_text(phrase)
    if not needle or not normalized:
        return []
    spans: list[tuple[int, int]] = []
    if " " in needle:
        hay = f" {normalized} "
        probe = f" {needle} "
        start = 0
        while True:
            idx = hay.find(probe, start)
            if idx < 0:
                break
            # hay = " " + normalized + " "; needle content begins at hay[idx+1]
            # → normalized index idx.
            norm_start = idx
            spans.append((norm_start, norm_start + len(needle)))
            start = idx + 1
    else:
        for m in re.finditer(rf"(?<!\w){re.escape(needle)}(?!\w)", normalized):
            spans.append((m.start(), m.end()))
    return spans


def _contains_phrase(normalized: str, phrase: str) -> bool:
    return bool(_phrase_spans(normalized, phrase))


def _any_phrase(normalized: str, phrases: Sequence[str]) -> bool:
    return any(_contains_phrase(normalized, p) for p in phrases)


@dataclass(frozen=True)
class _SafetyRule:
    rule_id: str
    level: RiskLevel
    action: SafetyAction
    domain: RiskDomain
    priority: int  # lower wins
    phrases: tuple[str, ...]


@dataclass(frozen=True)
class _Match:
    rule: _SafetyRule
    phrase: str
    start: int
    end: int


# Local negation immediately before an affirmative crisis span (Fix1 A02).
# After Fix2 apostrophe fold, don't→dont; I'm→im (patterns use folded forms).
_LOCAL_NEGATION_RE = re.compile(
    r"(?:^|\s)(?:"
    r"do\s+not|dont|does\s+not|did\s+not|"
    r"not|never|no\s+longer|"
    r"نمیخوام|نمیخواهم|"
    r"لا\s+اريد|لست|ليس"
    r")\s+(?:\w+\s+){0,4}$",
    re.IGNORECASE,
)

# Informational exclusions — suppress only danger spans *contained* by these cues.
_INFORMATIONAL_EXCLUSIONS: tuple[str, ...] = (
    "what are the symptoms of a heart attack",
    "what are the symptoms",
    "symptoms of a heart attack",
    "symptoms of heart attack",
    "what is a heart attack",
    "what does overdose mean",
    "what is overdose",
    "explain severe allergy",
    "what is a severe allergy",
    "define self harm",
    "what is self harm",
    "what is suicide",
    "tell me about chest pain",
    "what is a stroke",
    "what does poisoning mean",
    "what is paralysis",
    # Fix2: conceptual self-harm definition cues (occurrence-aware containment only).
    "what does want to die mean",
    "what does wanting to die mean",
    "what does suicidal mean",
    "what does suicide mean",
    "define want to die",
    "meaning of want to die",
    "اطلاعات درباره",
    "علائم حمله قلبی چیست",
    "علائم سکته قلبی چیست",
    "سکته چیست",
    "معنی اوردوز چیست",
    "اوردوز یعنی چه",
    "آلرژی شدید چیست",
    "خودکشی چیست",
    "شرح خودکشی",
    "ما اعراض النوبه القلبية",
    "ما اعراض السكتة",
    "ما معنى الجرعة الزائدة",
    "ما هي الحساسية الشديدة",
    "ما هو الانتحار",
)

# Denial phrases — cancel only overlapping / co-spanning crisis matches (A02).
_SELF_HARM_DENIAL: tuple[str, ...] = (
    "i am not suicidal",
    "im not suicidal",
    "i am not going to hurt myself",
    "not suicidal",
    "dont want to die",
    "do not want to die",
    "i do not want to die",
    "i dont want to die",
    "dont kill myself",
    "do not kill myself",
    "i dont kill myself",
    "i do not kill myself",
    "خودکشی نمیکنم",
    "قصد خودکشی ندارم",
    "نمیخوام به خودم اسیب بزنم",
    "نمیخواهم بمیرم",
    "نمیخواهم خودکشی کنم",
    "نمیخوام خودکشی کنم",
    # Fix3: past-tense FA denial — overlap-only; no bare-token global suppress.
    "نمیخواستم خودکشی کنم",
    "قصد نداشتم خودکشی کنم",
    "قصد خودکشی نداشتم",
    "لا اريد الانتحار",
    "لست انتحاريا",
    "لا اريد ان اموت",
)

_EMERGENCY_RULES: tuple[_SafetyRule, ...] = (
    _SafetyRule(
        "i4.rule.emergency.medical.v1",
        RiskLevel.EMERGENCY,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
        RiskDomain.MEDICAL_EMERGENCY,
        10,
        (
            "chest pain",
            "heart attack",
            "myocardial",
            "stroke",
            "not breathing",
            "cannot breathe",
            "cant breathe",
            "difficulty breathing",
            "severe bleeding",
            "unconscious",
            "seizure",
            "convulsion",
            "cannot move",
            "cant move",
            "paralysis",
            "درد قفسه سینه",
            "حمله قلبی",
            "سکته مغزی",
            "سکته قلبی",
            "سکته",
            "نمیتونم نفس بکشم",
            "نمیتوانم نفس بکشم",
            "دیگه نفس نمیکشم",
            "خونریزی شدید",
            "بیهوش",
            "تشنج",
            "فلج",
            "الم في الصدر",
            "نوبة قلبية",
            "سكتة",
            "لا استطيع التنفس",
            "لا استطيع ان اتنفس",
            "نزيف شديد",
            "فاقد الوعي",
            "تشنج",
            "شلل",
        ),
    ),
    _SafetyRule(
        "i4.rule.emergency.self_harm.v1",
        RiskLevel.EMERGENCY,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
        RiskDomain.SELF_HARM_CRISIS,
        20,
        (
            "kill myself",
            "want to die",
            "suicide attempt",
            "going to kill myself",
            "end my life",
            "cut my wrists",
            "cut my wrist",
            "hanging myself",
            "suicidal",
            "خودکشی میکنم",
            "خودکشی کنم",
            "میخواهم خودکشی کنم",
            "میخوام خودکشی کنم",
            "میخوام بمیرم",
            "میخواهم بمیرم",
            "خودم را بکشم",
            "اريد ان اموت",
            "ساقتل نفسي",
            "انتحار",
        ),
    ),
    _SafetyRule(
        "i4.rule.emergency.overdose.v1",
        RiskLevel.EMERGENCY,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
        RiskDomain.OVERDOSE_MEDICATION,
        30,
        (
            "i overdosed",
            "took too many pills",
            "overdose right now",
            "poisoned myself",
            "poisoning",
            "overdose",
            "اوردوز کردم",
            "زیادی قرص خوردم",
            "مسموم شدم با دارو",
            "مسمومیت دارویی",
            "تناولت جرعة زائدة",
            "تناولت الكثير من الحبوب",
        ),
    ),
    _SafetyRule(
        "i4.rule.emergency.allergy.v1",
        RiskLevel.EMERGENCY,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
        RiskDomain.SEVERE_ALLERGY,
        40,
        (
            "anaphylaxis",
            "severe allergic reaction",
            "severe allergic",
            "throat closing",
            "throat is closing",
            "cannot swallow from allergy",
            "شوک آلرژیک",
            "آلرژی شدید دارم الان",
            "گلو بسته شده از آلرژی",
            "حساسية مفرطة",
            "تفاعل تحسسي شديد",
        ),
    ),
)

# Ambiguous high-risk: terminal HIGH (no LLM). Demographic-alone tokens excluded.
_HIGH_RULES: tuple[_SafetyRule, ...] = (
    _SafetyRule(
        "i4.rule.high.urgent_neurologic.v1",
        RiskLevel.HIGH,
        SafetyAction.RETURN_HIGH_RESPONSE,
        RiskDomain.MEDICAL_EMERGENCY,
        50,
        (
            "slurred speech",
            "slurred speech now",
            "sudden weakness one side",
            "sudden weakness",
            "numbness face",
            "numbness arm",
            "vision loss",
            "sudden headache",
            "severe headache",
            "confusion sudden",
            "severe dizziness",
            "severe chest discomfort",
            "درد شدید قفسه",
            "ضعف ناگهانی یک طرف",
            "ضعف مفاجئ في جانب",
        ),
    ),
    _SafetyRule(
        "i4.rule.high.severe_symptom.v1",
        RiskLevel.HIGH,
        SafetyAction.RETURN_HIGH_RESPONSE,
        RiskDomain.MEDICAL_EMERGENCY,
        55,
        (
            "severe pain",
            "cant feel",
            "cannot feel",
            "تنگی نفس",
        ),
    ),
    _SafetyRule(
        "i4.rule.high.self_harm_topic.v1",
        RiskLevel.HIGH,
        SafetyAction.RETURN_HIGH_RESPONSE,
        RiskDomain.SELF_HARM_CRISIS,
        58,
        (
            "خودکشی",
        ),
    ),
)

_CAUTION_RULES: tuple[_SafetyRule, ...] = (
    _SafetyRule(
        "i4.rule.caution.medication_topic.v1",
        RiskLevel.CAUTION,
        SafetyAction.CONTINUE_WITH_CONSTRAINTS,
        RiskDomain.GENERAL,
        80,
        (
            "change my dose",
            "stop my medication",
            "start taking medicine",
            "دوز دارو را عوض",
            "دارو را قطع کنم",
            "غير جرعة الدواء",
        ),
    ),
    _SafetyRule(
        "i4.rule.caution.demographic_med_context.v1",
        RiskLevel.CAUTION,
        SafetyAction.CONTINUE_WITH_CONSTRAINTS,
        RiskDomain.GENERAL,
        85,
        (
            "pregnant and dose",
            "elderly medication",
            "child medication dose",
            "باردار و دوز",
            "سالمند و دارو",
        ),
    ),
)


_TEMPLATES: dict[str, dict[str, str]] = {
    "i4.tpl.emergency.v1": {
        "en": (
            "Please contact local emergency services or a clinician immediately. "
            "Do not wait for this chat. I cannot provide a diagnosis or emergency treatment instructions."
        ),
        "fa": (
            "لطفاً فوراً با خدمات اورژانس محلی یا پزشک تماس بگیرید. "
            "منتظر این گفتگو نمانید. من نمی‌توانم تشخیص بدهم یا دستور درمان اورژانسی ارائه کنم."
        ),
        "ar": (
            "يرجى الاتصال فوراً بخدمات الطوارئ المحلية أو بطبيب. "
            "لا تنتظر هذه المحادثة. لا يمكنني تقديم تشخيص أو تعليمات علاج طارئة."
        ),
    },
    "i4.tpl.emergency.self_harm.v1": {
        "en": (
            "Please contact local emergency services or a trusted person now. "
            "Do not wait for this chat. You are not alone; I cannot replace professional crisis care."
        ),
        "fa": (
            "لطفاً همین حالا با خدمات اورژانس محلی یا یک فرد مورد اعتماد تماس بگیرید. "
            "منتظر این گفتگو نمانید. شما تنها نیستید؛ من جایگزین مراقبت تخصصی بحران نیستم."
        ),
        "ar": (
            "يرجى الاتصال الآن بخدمات الطوارئ المحلية أو بشخص موثوق. "
            "لا تنتظر هذه المحادثة. لست وحدك؛ لا أحل محل الرعاية المهنية للأزمات."
        ),
    },
    "i4.tpl.high.v1": {
        "en": (
            "Please seek prompt medical care from a clinician as soon as possible. "
            "Do not delay urgent care for this chat. I can only offer general supportive information, not diagnosis or treatment orders."
        ),
        "fa": (
            "لطفاً در اسرع وقت به پزشک مراجعه کنید. مراقبت فوری را به‌خاطر این گفتگو به تأخیر نیندازید. "
            "من فقط اطلاعات حمایتی عمومی ارائه می‌دهم، نه تشخیص یا دستور درمان."
        ),
        "ar": (
            "يرجى طلب رعاية طبية عاجلة من طبيب في أقرب وقت. لا تؤخر الرعاية العاجلة لهذه المحادثة. "
            "يمكنني تقديم معلومات داعمة عامة فقط، لا تشخيصاً أو أوامر علاج."
        ),
    },
    "i4.tpl.fail_closed.v1": {
        "en": (
            "I cannot safely continue this response right now. "
            "If you may be in danger, contact local emergency services or a clinician."
        ),
        "fa": (
            "در حال حاضر نمی‌توانم این پاسخ را به‌صورت ایمن ادامه دهم. "
            "اگر ممکن است در خطر باشید، با خدمات اورژانس محلی یا پزشک تماس بگیرید."
        ),
        "ar": (
            "لا يمكنني مواصلة هذا الرد بأمان الآن. "
            "إذا كنت في خطر محتمل، فاتصل بخدمات الطوارئ المحلية أو بطبيب."
        ),
    },
    "i4.tpl.post_validation_fallback.v1": {
        "en": (
            "For your safety, I cannot provide that response. "
            "Please consult a qualified clinician. If you may be in immediate danger, contact local emergency services."
        ),
        "fa": (
            "برای ایمنی شما نمی‌توانم آن پاسخ را ارائه دهم. "
            "لطفاً با پزشک معتمد مشورت کنید. اگر خطر فوری دارید، با خدمات اورژانس محلی تماس بگیرید."
        ),
        "ar": (
            "لسلامتك، لا يمكنني تقديم هذا الجواب. "
            "يرجى استشارة طبيب مؤهل. إذا كنت في خطر فوري، فاتصل بخدمات الطوارئ المحلية."
        ),
    },
}


class SafetyRiskError(Exception):
    """Fail-closed safety engine failure (no raw content)."""


def _localized(template_id: str, language: LanguageCode) -> str:
    block = _TEMPLATES[template_id]
    return block.get(language) or block["en"]


def fail_closed_assessment(*, language: LanguageCode) -> RiskAssessment:
    """Trusted FAIL_CLOSED assessment — never embeds exception text."""
    lang: LanguageCode = language if language in ("fa", "ar", "en") else "en"
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=RiskLevel.NONE,
        action=SafetyAction.FAIL_CLOSED_RESPONSE,
        domain=RiskDomain.NONE,
        rule_id="i4.rule.classifier_failed.v1",
        language=lang,
    )


def build_fail_closed_response(*, language: LanguageCode) -> SafetyResponse:
    """Trusted fixed fail-closed wording for builder/assessor fallback."""
    lang: LanguageCode = language if language in ("fa", "ar", "en") else "en"
    tid = "i4.tpl.fail_closed.v1"
    return SafetyResponse(template_id=tid, localized_message=_localized(tid, lang))


def build_safety_response(assessment: RiskAssessment) -> SafetyResponse:
    """Build fixed localized wording for HIGH / EMERGENCY / fail-closed."""
    if assessment.action is SafetyAction.FAIL_CLOSED_RESPONSE:
        tid = "i4.tpl.fail_closed.v1"
    elif (
        assessment.level is RiskLevel.EMERGENCY
        and assessment.domain is RiskDomain.SELF_HARM_CRISIS
    ):
        tid = "i4.tpl.emergency.self_harm.v1"
    elif assessment.level is RiskLevel.EMERGENCY:
        tid = "i4.tpl.emergency.v1"
    elif assessment.level is RiskLevel.HIGH:
        tid = "i4.tpl.high.v1"
    else:
        tid = "i4.tpl.fail_closed.v1"
    return SafetyResponse(
        template_id=tid,
        localized_message=_localized(tid, assessment.language),
    )


def build_safety_response_safe(assessment: RiskAssessment) -> SafetyResponse:
    """Builder seam: never raises into a generator or ordinary response path."""
    try:
        resp = build_safety_response(assessment)
        if (
            not isinstance(resp.localized_message, str)
            or not resp.localized_message.strip()
        ):
            return build_fail_closed_response(language=assessment.language)
        return resp
    except Exception:
        return build_fail_closed_response(language=assessment.language)


def structured_caution_constraints() -> SafetyConstraints:
    """Fixed caution constraints for structured and compatibility — no user values."""
    return SafetyConstraints(
        policy_mode="structured_caution",
        no_diagnosis_or_dose_invention=True,
        no_unsupported_user_fact_invention=True,
        no_unsafe_logging=True,
        disclaimer_required=True,
        no_medication_start_stop=True,
    )


def _collect_matches(normalized: str, rules: Sequence[_SafetyRule]) -> list[_Match]:
    out: list[_Match] = []
    for rule in rules:
        for phrase in rule.phrases:
            for start, end in _phrase_spans(normalized, phrase):
                out.append(_Match(rule=rule, phrase=phrase, start=start, end=end))
    return out


def _collect_exclusion_spans(
    normalized: str, phrases: Sequence[str]
) -> list[tuple[int, int]]:
    spans: list[tuple[int, int]] = []
    for phrase in phrases:
        spans.extend(_phrase_spans(normalized, phrase))
    return spans


def _span_contained(inner: tuple[int, int], outer: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and outer[1] >= inner[1]


def _spans_overlap(a: tuple[int, int], b: tuple[int, int]) -> bool:
    return a[0] < b[1] and b[0] < a[1]


def _locally_negated(normalized: str, start: int) -> bool:
    prefix = normalized[:start]
    window = prefix[-48:] if len(prefix) > 48 else prefix
    if not window.strip():
        return False
    return bool(_LOCAL_NEGATION_RE.search(window + " "))


def assess_safety_risk(*, message: str, language: LanguageCode) -> RiskAssessment:
    """Deterministic risk assessment. Never logs or returns message text.

    Fix1: informational and denial exclusions apply per matched span only —
    never as a global message flag that erases independent current-danger spans.
    """
    if not isinstance(message, str):
        raise SafetyRiskError("invalid_message")
    if language not in ("fa", "ar", "en"):
        raise SafetyRiskError("invalid_language")

    normalized = normalize_safety_text(message)
    info_spans = _collect_exclusion_spans(normalized, _INFORMATIONAL_EXCLUSIONS)
    denial_spans = _collect_exclusion_spans(normalized, _SELF_HARM_DENIAL)
    candidates = _collect_matches(
        normalized, _EMERGENCY_RULES + _HIGH_RULES + _CAUTION_RULES
    )

    kept: list[_Match] = []
    for m in candidates:
        span = (m.start, m.end)
        # A01: suppress only spans contained by an informational exclusion cue.
        if m.rule.level in (RiskLevel.EMERGENCY, RiskLevel.HIGH):
            if any(_span_contained(span, info) for info in info_spans):
                continue
        # A02: self-harm — local negation or overlapping denial only.
        if (
            m.rule.domain is RiskDomain.SELF_HARM_CRISIS
            and m.rule.level in (RiskLevel.EMERGENCY, RiskLevel.HIGH)
        ):
            if _locally_negated(normalized, m.start):
                continue
            if any(_spans_overlap(span, den) for den in denial_spans):
                continue
        kept.append(m)

    if not kept:
        return RiskAssessment(
            registry_version=REGISTRY_VERSION,
            level=RiskLevel.NONE,
            action=SafetyAction.CONTINUE,
            domain=RiskDomain.NONE,
            rule_id="i4.rule.none.v1",
            language=language,
        )

    kept.sort(key=lambda m: (m.rule.priority, m.rule.rule_id, m.start))
    winner = kept[0].rule
    return RiskAssessment(
        registry_version=REGISTRY_VERSION,
        level=winner.level,
        action=winner.action,
        domain=winner.domain,
        rule_id=winner.rule_id,
        language=language,
    )


def assess_safety_risk_safe(*, message: str, language: LanguageCode) -> RiskAssessment:
    """Fail-closed public seam: classifier exceptions become FAIL_CLOSED_RESPONSE."""
    try:
        return assess_safety_risk(message=message, language=language)
    except Exception:
        return fail_closed_assessment(language=language)  # type: ignore[arg-type]


def validate_generated_response(
    *,
    text: str,
    language: LanguageCode,
) -> PostGenerationSafetyResult:
    """Wrap Gate3 text validator without editing that module. No regeneration."""
    try:
        from backend.app.services.gate3.safety_validator import validate_response_text

        ok, code = validate_response_text(text or "")
        if ok:
            return PostGenerationSafetyResult(
                status=PostGenerationSafetyStatus.SAFE,
                violation_code=None,
                message=text or "",
            )
        fallback = _localized("i4.tpl.post_validation_fallback.v1", language)
        return PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.REPLACED,
            violation_code=code or "unsafe_generation",
            message=fallback,
        )
    except Exception:
        fallback = _localized("i4.tpl.fail_closed.v1", language)
        return PostGenerationSafetyResult(
            status=PostGenerationSafetyStatus.FAILED_CLOSED,
            violation_code="validator_exception",
            message=fallback,
        )


def list_template_strings() -> tuple[str, ...]:
    """Expose all I4 template strings for static scans (tests)."""
    texts: list[str] = []
    for block in _TEMPLATES.values():
        texts.extend(block.values())
    return tuple(texts)


def requires_terminal_safety_response(assessment: RiskAssessment) -> bool:
    return assessment.action in (
        SafetyAction.RETURN_HIGH_RESPONSE,
        SafetyAction.RETURN_EMERGENCY_RESPONSE,
        SafetyAction.FAIL_CLOSED_RESPONSE,
    )
