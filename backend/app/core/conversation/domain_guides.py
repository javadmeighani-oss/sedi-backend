"""R-074 step 2 - ANSWER GUIDES for knowledge-type topics (layer 6 of the six-layer model: behavioural principles per domain).

A guide fixes the SHAPE of a complete answer (what a professional covers for this topic) - never the medical facts. Facts, numbers
and doses come only from the governed knowledge block and the user's recorded facts; nothing here is a medical claim. A guide is
injected only when the user's message is about its topic, so a normal chat turn pays no extra tokens. Detection is by concept
words in fa / ar / en (a topic word anywhere in the message), not by one exact sentence.
"""
from __future__ import annotations

import re
from typing import Optional

_HEADER = (
    "[ANSWER GUIDE - shape only] Topic guide for this turn. If the user is only describing a personal problem and key facts are still missing, keep the personal-problem shape (one line of empathy, at most two actions, one question). If the user is answering a question you asked earlier, that answer IS a fact (count it). As soon as two or three facts are known, or the user asks for a plan, a how-to, an explanation or 'tell me about it', give a COMPLETE, practical, personal answer in the user's language, following the outline below, in plain text with short plain-word section labels ending with a colon (no markdown, no asterisks). Take every fact, number and dose ONLY from the knowledge block and the user's recorded facts; for an aspect they do not cover, skip it or ask the ONE fact you need (never invent). Real danger signs -> urge real help now. End with one concrete next step and a time."
)

# Javad 2026-11-09 (R-065, the CLASS): «کمرم کمی درد میکنه» / «پام درد می‌کنه» / «my lower back hurts» / «ظهري يؤلمني» carry no fixed phrase like
# «کمردرد», yet they are the same topic. Concept = a body part (with possessive suffix) near a pain word, in either order.
_FA_PART = (
    r"(?<![؀-ۿ])(?:کمر|گردن|زانو|شانه|شونه|مفصل|مفاصل|مهره|مهره‌های|ستون\s*فقرات|پشت|مچ|آرنج|ران|لگن|پاشنه|عضله|عضلات|ماهیچه|بازو|ساق|کف\s*پا|پا|دست)"
    r"(?:ام|م|ت|ش|مان|تان|شان|ها|های)?"
)
_FA_PAIN = r"(?:درد|ناراحتی|گرفتگی|خشکی|کوفتگی|تیر\s*(?:می[\s‌]?)?کش|سوزش|ورم|کشیدگی|گرفته)"
_AR_PART = r"(?:الظهر|ظهري|ظهر|الرقبة|رقبتي|الركبة|ركبتي|الكتف|كتفي|المفاصل|مفاصلي|العضلات|عضلاتي|الساق|ساقي|القدم|قدمي|الورك|وركي)"
_AR_PAIN = r"(?:ألم|الم|وجع|يؤلمني|تؤلمني|يوجعني|توجعني|يؤلم|تؤلم)"
_EN_PART = r"(?:back|neck|knee|knees|shoulder|shoulders|hip|hips|wrist|ankle|elbow|leg|legs|foot|feet|joint|joints|muscle|muscles|spine)"
_EN_PAIN = r"(?:pain|painful|hurts?|hurting|ache|aching|aches|sore|stiff|stiffness|cramp|cramps)"
_MSK_CONCEPT = (
    rf"{_FA_PART}.{{0,30}}{_FA_PAIN}|{_FA_PAIN}.{{0,12}}{_FA_PART}|"
    rf"{_AR_PART}.{{0,25}}{_AR_PAIN}|{_AR_PAIN}.{{0,12}}{_AR_PART}|"
    rf"\b{_EN_PART}\b.{{0,25}}\b{_EN_PAIN}\b|\b{_EN_PAIN}\b.{{0,15}}\b{_EN_PART}\b"
)

_GUIDES: tuple[tuple[str, re.Pattern[str], str], ...] = (
    (
        "sleep",
        re.compile(
            r"خواب|بی\s*[‌]?\s*خوابی|بیدار|کابوس|چرت|\bsleep|insomnia|\bwake\s*up|\bwaking\b|\bnap(?:s|ping)?\b|(?<![؀-ۿ])(?:نوم|أرق|ارق|نعاس)|استيقظ",
            re.IGNORECASE,
        ),
        "SLEEP: what the pattern suggests (hypotheses with reasons) | tonight's plan (fixed wake time, wind-down, light and screens, caffeine and alcohol, what to do when awake in bed) | one-week plan with a simple sleep diary | what usually keeps the problem going (stress, late meals, naps, noise, heat) | warning signs that need real help, as the knowledge block lists them.",
    ),
    (
        "meal_plan",
        re.compile(
            r"برنامه\s*غذایی|برنامه\s*ی\s*غذایی|رژیم|تغذیه|کاهش\s*وزن|اضافه\s*وزن|چاقی|لاغری|وعده|\bdiet\b|meal\s*plan|nutrition|weight\s*loss|\beating\b|نظام\s*غذائي|حمية|تغذية|وجبات|وزن",
            re.IGNORECASE,
        ),
        "MEAL PLAN: the goal and what is known about this person (allergies, conditions, medicines, budget, cooking time) | the principles of the plan in plain words | a concrete day or week layout by meal | portions or amounts only if the knowledge gives them | foods to limit and why | swaps for dislikes or allergies | what to track and when to review | warning signs from the knowledge block.",
    ),
    (
        "exercise_plan",
        re.compile(
            r"ورزش|تمرین|حرکات|برنامه\s*ورزشی|پیاده\s*روی|\bexercis|workout|\btraining\b|fitness|\bstretch|تمارين|رياضة|تمرين|مشي",
            re.IGNORECASE,
        ),
        "EXERCISE PLAN: the goal and limits of this person (conditions, pain, age, equipment, time) | a starting level and how to progress week by week | a concrete weekly layout (type, duration, frequency) | warm-up and cool-down | how to know it is going well and how to adjust | stop-and-get-help signs, as the knowledge block lists them.",
    ),
    (
        "msk_pain",
        re.compile(
            r"کمر\s*درد|کمردرد|گردن\s*درد|گردن‌درد|درد\s*(?:کمر|گردن|زانو|شانه|مفصل|مفاصل|عضله|عضلات|پا|پاشنه|دست|مچ|ستون)|دیسک|آرتروز|کشیدگی|گرفتگی\s*عضله|سیاتیک|"
            r"\b(?:back|neck|knee|shoulder|joint|muscle|heel|hip|wrist)\s+pain|sciatica|arthritis|sprain|strain|"
            r"ألم\s*(?:الظهر|الرقبة|الركبة|الكتف|المفاصل|العضل)|الم\s*(?:الظهر|الرقبة|الركبة|الكتف|المفاصل|العضل)|عرق\s*النسا|" + _MSK_CONCEPT,
            re.IGNORECASE | re.DOTALL,
        ),
        "MUSCLE AND JOINT PAIN: where, since when, what triggers and eases it (ask only what is missing) | the most likely everyday causes in plain words and how to tell them apart | what to do now (activity, positions, heat or cold, pacing) | simple gentle movements or exercises step by step, from the knowledge block | what to avoid | how long recovery usually takes and how to progress | red flags needing real help now, as the knowledge block lists them.",
    ),
    (
        "labs",
        re.compile(
            r"آزمایش|قند\s*خون|کلسترول|هموگلوبین|لیپید|چربی\s*خون|\bcbc\b|blood\s*test|lab\s*(?:test|result)|cholesterol|hemoglobin|hba1c|تحليل|تحاليل|نتيجة\s*التحليل|سكر\s*الدم",
            re.IGNORECASE,
        ),
        "TEST RESULTS: restate each value with its unit and the reference range printed on the document | which are in range, high or low and what each usually reflects in plain words | how they connect to this person's recorded picture and history | what to do in daily life about them | what to recheck and when | values that need real help now, as the knowledge block lists them.",
    ),
    (
        "elder_care",
        re.compile(
            r"سالمند|پیری|زوال\s*عقل|آلزایمر|فراموشی|\belderly\b|older\s*(?:adult|people|person)|dementia|alzheimer|caregiv|كبار\s*السن|المسنين|الخرف|الزهايمر",
            re.IGNORECASE,
        ),
        "ELDER CARE: the person's abilities, risks and routine | safety at home (falls, medicines, nutrition, hydration) | daily routine and activity suited to them | communication and emotional support, including for the caregiver | when to involve professionals or services | warning signs needing real help now, as the knowledge block lists them.",
    ),
    (
        "chronic",
        re.compile(
            r"دیابت|فشار\s*خون|قند\s*بالا|آسم|میگرن|ریفلاکس|پوکی\s*استخوان|کم\s*خونی|تیروئید|\bdiabet|hypertension|blood\s*pressure|asthma|migraine|reflux|\bgerd\b|osteoporosis|anemia|anaemia|thyroid|السكري|ضغط\s*الدم|الربو|الصداع\s*النصفي|الارتجاع",
            re.IGNORECASE,
        ),
        "LONG-TERM CONDITION: what it is and how it behaves in plain words | daily self-care that matters most (food, movement, sleep, stress, medicines the person already takes) | what to monitor and how often | typical triggers and how to avoid them | a step-by-step routine for the week | complications to prevent | danger signs needing real help now, as the knowledge block lists them.",
    ),
)

_MAX_GUIDES = 2


def _ids_for(text: str) -> list[str]:
    return [gid for gid, rx, _ in _GUIDES if rx.search(text)][:_MAX_GUIDES]


def matched_guides(message: Optional[str], previous: Optional[list[str]] = None) -> list[str]:
    """Ids of the guides whose topic the message is about (at most two, in the order above).

    A follow-up that carries no topic word of its own («نه روی مهره‌های پایین کمرم است … رانندگی طولانی») stays on the topic of the
    user's last turns (``previous``, newest first): the conversation, not one sentence, decides the guide."""
    text = (message or "").strip()
    if not text:
        return []
    ids = _ids_for(text)
    if not ids:
        for earlier in (previous or [])[:2]:
            ids = _ids_for((earlier or "").strip())
            if ids:
                break
    return ids


def answer_guide_block(message: Optional[str], previous: Optional[list[str]] = None) -> Optional[str]:
    """The system block to add for this message, or None when it is not a knowledge-type topic."""
    ids = matched_guides(message, previous)
    if not ids:
        return None
    body = "\n".join(text for gid, _, text in _GUIDES if gid in ids)
    return _HEADER + body
