"""Versioned SCIS-01 synthetic evaluation corpus (no PHI)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

CORPUS_VERSION = "scis-eval-corpus-v1"
# Explicit label for every synthetic row. Not a source citation.
EVIDENCE_LABEL = "SYNTHETIC"
# Live OpenAI measurement budget. Not a relevance cutoff or a clinical decision.
SEMANTIC_EVAL_INPUT_BUDGET = 40


@dataclass(frozen=True)
class EvalDoc:
    doc_id: str
    language: str
    domain: str
    title: str
    text: str
    entity_tags: tuple[str, ...]
    evidence_label: str = EVIDENCE_LABEL


@dataclass(frozen=True)
class EvalQuery:
    query_id: str
    language: str
    text: str
    relevant_doc_ids: tuple[str, ...]
    kind: str  # exact | paraphrase | cross_lang | safety_filter
    evidence_label: str = EVIDENCE_LABEL
    topic: str = ""


DOCS: List[EvalDoc] = [
    EvalDoc(
        "en_als_care",
        "en",
        "neurology",
        "ALS supportive care",
        "Amyotrophic lateral sclerosis (ALS) supportive care includes respiratory monitoring, "
        "nutrition support, and physiotherapy. Contraindication: do not invent curative claims.",
        ("ALS", "amyotrophic lateral sclerosis"),
    ),
    EvalDoc(
        "en_ms_fatigue",
        "en",
        "neurology",
        "MS fatigue guidance",
        "Multiple sclerosis (MS) fatigue management may include energy conservation, graded activity, "
        "and sleep hygiene. Warning: sudden neurological deficits need urgent evaluation.",
        ("MS", "multiple sclerosis", "ms"),
    ),
    EvalDoc(
        "en_nutrition_fiber",
        "en",
        "nutrition",
        "Fiber intake",
        "Adequate dietary fiber supports digestive health. Adults often benefit from vegetables, "
        "fruits, and whole grains as part of routine lifestyle guidance.",
        ("fiber", "nutrition"),
    ),
    EvalDoc(
        "en_exercise_brisk",
        "en",
        "exercise",
        "Brisk walking",
        "Brisk walking is a common lifestyle exercise for cardiovascular fitness when medically appropriate.",
        ("exercise", "walking"),
    ),
    EvalDoc(
        "fa_als",
        "fa",
        "neurology",
        "مراقبت ALS",
        "اسکلروز جانبی آمیوتروفیک (ALS) نیازمند مراقبت حمایتی تنفسی و تغذیه است. "
        "هشدار: ادعای درمان قطعی نباید مطرح شود.",
        ("ALS",),
    ),
    EvalDoc(
        "fa_ms",
        "fa",
        "neurology",
        "خستگی ام‌اس",
        "در مولتیپل اسکلروزیس (MS) مدیریت خستگی شامل حفظ انرژی و بهداشت خواب است.",
        ("MS", "ms"),
    ),
    EvalDoc(
        "fa_yeh_kaf",
        "fa",
        "lifestyle",
        "فعالیت روزانه",
        "فعالیت بدنی منظم در سبک زندگی سالم توصیه می‌شود.",  # Persian Yeh/Kaf forms
        ("lifestyle",),
    ),
    EvalDoc(
        "ar_als",
        "ar",
        "neurology",
        "رعاية التصلب الجانبي",
        "التصلب الجانبي الضموري (ALS) يحتاج رعاية تنفسية ودعمًا غذائيًا. "
        "تحذير: لا تقدم ادعاءات علاجية غير مؤكدة.",
        ("ALS",),
    ),
    EvalDoc(
        "ar_ms",
        "ar",
        "neurology",
        "التعب في التصلب المتعدد",
        "في مرض التصلب المتعدد (MS) يمكن أن يشمل تدبير التعب حفظ الطاقة ونظافة النوم.",
        ("MS", "ms"),
    ),
    EvalDoc(
        "ar_routine",
        "ar",
        "lifestyle",
        "الروتين اليومي",
        "الروتين اليومي الصحي يشمل النوم المنتظم والنشاط البدني المعتدل.",
        ("routine",),
    ),
    EvalDoc(
        "en_stress_care",
        "en",
        "mental_health_psychology",
        "SYNTHETIC stress self-care",
        "SYNTHETIC EVALUATION EVIDENCE. Everyday stress self-care may include a regular routine, "
        "brief walks, and time with supportive people. This is not a diagnosis or a treatment order.",
        ("SYNTHETIC", "stress", "wellbeing"),
    ),
    EvalDoc(
        "fa_stress_care",
        "fa",
        "mental_health_psychology",
        "SYNTHETIC مراقبت استرس",
        "SYNTHETIC EVALUATION EVIDENCE. مراقبت روزمره از استرس می‌تواند شامل برنامه منظم، "
        "پیاده‌روی کوتاه و بودن با افراد حمایتگر باشد. این متن تشخیص یا دستور درمان نیست.",
        ("SYNTHETIC", "stress", "wellbeing"),
    ),
    EvalDoc(
        "ar_stress_care",
        "ar",
        "mental_health_psychology",
        "SYNTHETIC العناية بالإجهاد",
        "SYNTHETIC EVALUATION EVIDENCE. العناية اليومية بالإجهاد قد تشمل روتينًا منتظمًا "
        "ومشيًا قصيرًا ووجود أشخاص داعمين. هذا النص ليس تشخيصًا ولا أمرًا علاجيًا.",
        ("SYNTHETIC", "stress", "wellbeing"),
    ),
    EvalDoc(
        "en_ms_hard_negative",
        "en",
        "neurology",
        "SYNTHETIC migraine hard negative",
        "SYNTHETIC EVALUATION EVIDENCE. Migraine comfort may include a quiet room, fluids, "
        "and rest. This neurology note is not about multiple sclerosis.",
        ("SYNTHETIC", "HARD_NEGATIVE", "ms"),
    ),
    EvalDoc(
        "en_stress_hard_negative",
        "en",
        "mental_health_psychology",
        "SYNTHETIC grief hard negative",
        "SYNTHETIC EVALUATION EVIDENCE. Grief support may include time, remembrance, and "
        "company. This wellbeing note is not a stress self-care plan.",
        ("SYNTHETIC", "HARD_NEGATIVE", "stress"),
    ),
    EvalDoc(
        "en_safety_limitation",
        "en",
        "neurology",
        "SYNTHETIC safety limitation",
        "SYNTHETIC EVALUATION EVIDENCE. Educational information must not claim a cure and "
        "must not tell a person to stop prescribed care.",
        ("SYNTHETIC", "safety"),
    ),
]


QUERIES: List[EvalQuery] = [
    EvalQuery("q_en_als_exact", "en", "ALS supportive care respiratory", ("en_als_care",), "exact"),
    EvalQuery("q_en_ms_para", "en", "how to manage fatigue in multiple sclerosis", ("en_ms_fatigue",), "paraphrase"),
    EvalQuery("q_en_fiber", "en", "dietary fiber vegetables fruits", ("en_nutrition_fiber",), "exact"),
    EvalQuery("q_en_walk", "en", "brisk walking exercise", ("en_exercise_brisk",), "exact"),
    EvalQuery("q_fa_als", "fa", "مراقبت حمایتی ALS تنفسی", ("fa_als",), "exact"),
    EvalQuery("q_fa_ms", "fa", "خستگی در ام اس", ("fa_ms",), "paraphrase"),
    EvalQuery("q_fa_variant", "fa", "فعاليت بدني منظم", ("fa_yeh_kaf",), "exact"),  # Arabic Yeh/Kaf variants in query
    EvalQuery("q_ar_als", "ar", "رعاية ALS التنفسية", ("ar_als",), "exact"),
    EvalQuery("q_ar_ms", "ar", "تعب التصلب المتعدد", ("ar_ms",), "paraphrase"),
    EvalQuery("q_ar_routine", "ar", "الروتين اليومي الصحي", ("ar_routine",), "exact"),
    EvalQuery("q_cross_als", "en", "amyotrophic lateral sclerosis nutrition support", ("en_als_care", "fa_als", "ar_als"), "cross_lang"),
    EvalQuery(
        "q_en_ms_matrix",
        "en",
        "What daily care helps fatigue in multiple sclerosis?",
        ("en_ms_fatigue", "fa_ms", "ar_ms"),
        "cross_lang",
        topic="ms",
    ),
    EvalQuery(
        "q_fa_ms_matrix",
        "fa",
        "برای خستگی مولتیپل اسکلروزیس چه مراقبت روزانه‌ای مفید است؟",
        ("en_ms_fatigue", "fa_ms", "ar_ms"),
        "cross_lang",
        topic="ms",
    ),
    EvalQuery(
        "q_ar_ms_matrix",
        "ar",
        "ما الرعاية اليومية المفيدة لتعب التصلب المتعدد؟",
        ("en_ms_fatigue", "fa_ms", "ar_ms"),
        "cross_lang",
        topic="ms",
    ),
    EvalQuery(
        "q_en_stress_matrix",
        "en",
        "What everyday self-care helps with stress?",
        ("en_stress_care", "fa_stress_care", "ar_stress_care"),
        "cross_lang",
        topic="stress",
    ),
    EvalQuery(
        "q_fa_stress_matrix",
        "fa",
        "برای مراقبت روزمره از استرس چه کارهایی مفید است؟",
        ("en_stress_care", "fa_stress_care", "ar_stress_care"),
        "cross_lang",
        topic="stress",
    ),
    EvalQuery(
        "q_ar_stress_matrix",
        "ar",
        "ما العناية اليومية المفيدة للإجهاد؟",
        ("en_stress_care", "fa_stress_care", "ar_stress_care"),
        "cross_lang",
        topic="stress",
    ),
    EvalQuery(
        "q_en_ms_negation",
        "en",
        "Multiple sclerosis is not cured by stopping prescribed care.",
        ("en_safety_limitation",),
        "safety_filter",
        topic="ms",
    ),
]


def docs_by_id() -> Dict[str, EvalDoc]:
    return {d.doc_id: d for d in DOCS}


def semantic_eval_input_count() -> int:
    """Doc texts plus query texts. Not a clinical decision."""
    return len(DOCS) + len(QUERIES)


def language_pair_matrix(queries: Optional[List[EvalQuery]] = None) -> set[tuple[str, str]]:
    """Query language × evidence language. Evidence language is not rewritten."""
    lookup = docs_by_id()
    pairs: set[tuple[str, str]] = set()
    for query in queries if queries is not None else QUERIES:
        if query.topic not in {"ms", "stress"} or query.kind != "cross_lang":
            continue
        for doc_id in query.relevant_doc_ids:
            doc = lookup[doc_id]
            pairs.add((query.language, doc.language))
    return pairs
