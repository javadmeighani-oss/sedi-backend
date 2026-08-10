"""Versioned SCIS-01 synthetic evaluation corpus (no PHI)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

CORPUS_VERSION = "scis-eval-corpus-v1"


@dataclass(frozen=True)
class EvalDoc:
    doc_id: str
    language: str
    domain: str
    title: str
    text: str
    entity_tags: tuple[str, ...]


@dataclass(frozen=True)
class EvalQuery:
    query_id: str
    language: str
    text: str
    relevant_doc_ids: tuple[str, ...]
    kind: str  # exact | paraphrase | cross_lang | safety_filter


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
        ("MS", "multiple sclerosis"),
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
        ("MS",),
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
        ("MS",),
    ),
    EvalDoc(
        "ar_routine",
        "ar",
        "lifestyle",
        "الروتين اليومي",
        "الروتين اليومي الصحي يشمل النوم المنتظم والنشاط البدني المعتدل.",
        ("routine",),
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
]


def docs_by_id() -> Dict[str, EvalDoc]:
    return {d.doc_id: d for d in DOCS}
