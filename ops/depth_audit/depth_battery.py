"""R-074 step 1 - READ-ONLY depth battery for Sedi's knowledge layer (runs inside the backend container via stdin).

It asks the SAME retrieval + renderer the chat uses (limit=5, 4400-char care block) a fixed set of knowledge-type questions
in English and Persian and reports, per question: how many governed units came back, how many characters the model would
really receive, and how many of the expected concepts that text covers. It never writes (rollback only), never prints user
data, never calls the chat model. Output lines start with `DEPTH|`.
"""
from __future__ import annotations

import json
import os
import statistics
import time

# (topic id, domain family, English query, Persian query, expected concept groups - any synonym of a group counts)
BATTERY = [
    ("sleep_insomnia", "sleep", "how to treat insomnia and improve sleep", "چطور بی‌خوابی را درمان کنم و خوابم بهتر شود",
     [("sleep hygiene",), ("cognitive behavioral", "cbt"), ("caffeine",), ("bedtime", "sleep schedule", "regular"), ("light", "screen"), ("relax",)]),
    ("sleep_waking", "sleep", "why do I wake up at night and cannot fall back asleep", "چرا شب‌ها از خواب بیدار می‌شوم و دوباره خوابم نمی‌برد",
     [("stress", "anxiety"), ("alcohol", "caffeine"), ("sleep apnea", "apnea"), ("routine", "schedule"), ("bedroom", "environment")]),
    ("diet_diabetes", "nutrition", "meal plan for type 2 diabetes", "برنامه غذایی برای دیابت نوع ۲",
     [("carbohydrate",), ("fiber",), ("glycemic",), ("portion",), ("vegetable",), ("sugar",)]),
    ("diet_weight_loss", "nutrition", "healthy weight loss diet plan", "رژیم غذایی سالم برای کاهش وزن",
     [("calorie", "energy"), ("protein",), ("portion",), ("vegetable", "fruit"), ("whole grain", "fiber"), ("sugar",)]),
    ("diet_hypertension", "nutrition", "diet for high blood pressure", "رژیم غذایی برای فشار خون بالا",
     [("sodium", "salt"), ("potassium",), ("dash",), ("vegetable", "fruit"), ("alcohol",)]),
    ("diet_cholesterol", "nutrition", "foods to lower cholesterol", "غذاهای کاهنده کلسترول",
     [("saturated fat",), ("fiber",), ("omega", "fish"), ("nuts",), ("whole grain",)]),
    ("exercise_beginner", "exercise", "beginner exercise plan how to start", "برنامه ورزشی مبتدی از کجا شروع کنم",
     [("150 minutes", "moderate"), ("strength", "resistance"), ("gradual", "progress", "slowly"), ("warm", "stretch"), ("walking",)]),
    ("exercise_elderly", "exercise", "exercise for older adults balance and strength", "ورزش برای سالمندان تعادل و قدرت",
     [("balance",), ("strength", "resistance"), ("fall",), ("walking",), ("flexibility", "stretch")]),
    ("exercise_heart", "exercise", "safe exercise with heart disease", "ورزش ایمن برای بیماران قلبی",
     [("moderate",), ("warning", "symptom", "chest pain"), ("cardiac rehabilitation", "rehab"), ("gradual", "progress"), ("heart rate",)]),
    ("msk_low_back", "musculoskeletal", "low back pain causes self care and exercises", "کمردرد علل مراقبت و حرکات اصلاحی",
     [("posture",), ("stretch", "exercise"), ("heat", "ice", "cold"), ("red flag", "numbness", "weakness"), ("stay active", "movement"), ("sciatica", "nerve")]),
    ("msk_neck", "musculoskeletal", "neck pain causes and treatment", "گردن درد علل و درمان",
     [("posture",), ("stretch", "exercise"), ("screen", "workstation", "ergonomic"), ("heat", "cold", "ice"), ("numbness", "tingling")]),
    ("msk_knee", "musculoskeletal", "knee pain osteoarthritis management", "درد زانو و آرتروز مدیریت",
     [("strengthening", "exercise"), ("weight",), ("swelling", "inflammation"), ("low impact", "swimming", "cycling"), ("cartilage", "joint")]),
    ("msk_shoulder", "musculoskeletal", "shoulder pain rotator cuff what to do", "درد شانه و کشیدگی عضله چه کنم",
     [("rotator cuff",), ("rest", "avoid"), ("stretch", "exercise"), ("ice", "heat"), ("physiotherapy", "physical therapy")]),
    ("msk_strain", "musculoskeletal", "muscle strain recovery and when to see help", "ریکاوری کشیدگی عضله",
     [("rest",), ("ice",), ("compression",), ("elevation", "elevate"), ("gradual return", "gradually")]),
    ("msk_plantar", "musculoskeletal", "heel pain plantar fasciitis treatment", "درد پاشنه پا فاشییت پلانتار درمان",
     [("stretch",), ("footwear", "shoes", "arch"), ("rest",), ("ice",), ("calf",)]),
    ("dis_diabetes", "disease", "type 2 diabetes self care and complications", "مراقبت از دیابت نوع ۲ و عوارض",
     [("blood sugar", "glucose"), ("foot",), ("eye",), ("kidney",), ("exercise", "activity"), ("a1c", "hba1c")]),
    ("dis_hypertension", "disease", "high blood pressure treatment and lifestyle", "فشار خون بالا درمان و سبک زندگی",
     [("salt", "sodium"), ("exercise", "activity"), ("weight",), ("medication", "medicine"), ("monitor", "measure")]),
    ("dis_asthma", "disease", "asthma triggers and action plan", "آسم محرک‌ها و برنامه عمل",
     [("trigger",), ("inhaler",), ("action plan",), ("peak flow",), ("symptom",)]),
    ("dis_migraine", "disease", "migraine triggers prevention and treatment", "میگرن محرک‌ها پیشگیری و درمان",
     [("trigger",), ("sleep",), ("stress",), ("medication", "medicine"), ("diary", "track")]),
    ("dis_reflux", "disease", "acid reflux GERD lifestyle changes", "ریفلاکس معده تغییر سبک زندگی",
     [("trigger food", "spicy", "fatty"), ("meal", "eating"), ("head", "elevate", "lying down"), ("weight",), ("smoking", "alcohol")]),
    ("dis_osteoporosis", "disease", "osteoporosis prevention calcium vitamin D exercise", "پیشگیری از پوکی استخوان",
     [("calcium",), ("vitamin d",), ("weight-bearing", "weight bearing", "resistance"), ("fall",), ("bone density",)]),
    ("dis_anemia", "disease", "iron deficiency anemia causes and diet", "کم‌خونی فقر آهن علل و تغذیه",
     [("iron",), ("vitamin c",), ("fatigue", "tired"), ("meat", "beans", "leafy"), ("blood test", "hemoglobin")]),
    ("mind_anxiety", "psychology", "how to manage anxiety and panic", "مدیریت اضطراب و حمله پانیک",
     [("breathing",), ("grounding", "mindfulness"), ("cognitive", "thoughts"), ("exercise",), ("sleep",), ("avoidance", "gradual exposure")]),
    ("mind_depression", "psychology", "low mood and depression self help", "کم‌حوصلگی و افسردگی چه کنم",
     [("behavioral activation", "activity", "activities"), ("social", "connect"), ("sleep",), ("exercise",), ("routine",)]),
    ("elder_falls", "elder", "fall prevention for older people at home", "پیشگیری از زمین‌خوردن سالمند در خانه",
     [("balance",), ("home", "hazard"), ("footwear", "shoes"), ("vision", "eye"), ("medication",), ("strength",)]),
    ("elder_dementia", "elder", "caring for a family member with dementia", "مراقبت از بیمار مبتلا به زوال عقل در خانه",
     [("routine",), ("communication", "communicate"), ("safety",), ("caregiver", "carer"), ("memory",)]),
    ("lab_reading", "labs", "how to understand blood test results cholesterol hemoglobin", "نتایج آزمایش خون را چطور بفهمم",
     [("reference range", "normal range"), ("cholesterol", "ldl", "hdl"), ("hemoglobin",), ("glucose", "sugar"), ("doctor", "healthcare")]),
]

CHAT_LIMIT = 5
CHAT_BLOCK_CHARS = 4400


def _concept_cover(text: str, groups) -> float:
    low = text.lower()
    hit = sum(1 for g in groups if any(s in low for s in g))
    return hit / max(1, len(groups))


def _run_one(db, query: str, lang: str, groups):
    from backend.app.services.i5.reference_renderer import format_care_context_block, render_grounded_answer
    from backend.app.services.i5.runtime_knowledge_retrieval import retrieve_knowledge_context

    t0 = time.time()
    res = retrieve_knowledge_context(db, query, language=lang, limit=CHAT_LIMIT, enqueue_gap_on_empty=False)
    items = list(res.items)
    raw_text = " ".join(i.normalized_statement or "" for i in items)
    try:
        grounded = render_grounded_answer(res.to_dict(), language=lang, user_requested_sources=True)
        block = str(format_care_context_block(grounded, max_chars=CHAT_BLOCK_CHARS) or "")
    except Exception:
        block = ""
    db.rollback()
    return {
        "items": len(items),
        "unit_chars_total": len(raw_text),
        "unit_chars_avg": int(len(raw_text) / len(items)) if items else 0,
        "domains": sorted({i.domain for i in items}),
        "langs": sorted({i.language for i in items}),
        "block_chars": len(block),
        "cover_units": round(_concept_cover(raw_text, groups), 2),
        "cover_block": round(_concept_cover(block, groups), 2),
        "status": res.status,
        "ms": int((time.time() - t0) * 1000),
    }


def main() -> None:
    from backend.app.database import get_db

    db = next(get_db())
    rows = []
    try:
        for tid, fam, q_en, q_fa, groups in BATTERY:
            for lang, q in (("en", q_en), ("fa", q_fa)):
                try:
                    r = _run_one(db, q, lang, groups)
                except Exception as e:  # never break the audit on one query
                    db.rollback()
                    r = {"items": -1, "error": type(e).__name__}
                r.update({"topic": tid, "family": fam, "lang": lang})
                rows.append(r)
                print("DEPTH|row|" + json.dumps(r, ensure_ascii=False))
        for lang in ("en", "fa"):
            sub = [r for r in rows if r["lang"] == lang and r.get("items", -1) >= 0]
            if not sub:
                continue
            summ = {
                "lang": lang,
                "queries": len(sub),
                "zero_items": sum(1 for r in sub if r["items"] == 0),
                "avg_items": round(statistics.mean(r["items"] for r in sub), 2),
                "median_block_chars": int(statistics.median(r["block_chars"] for r in sub)),
                "avg_cover_units": round(statistics.mean(r["cover_units"] for r in sub), 2),
                "avg_cover_block": round(statistics.mean(r["cover_block"] for r in sub), 2),
                "cover_block_lt_050": sum(1 for r in sub if r["cover_block"] < 0.5),
            }
            print("DEPTH|summary|" + json.dumps(summ, ensure_ascii=False))
            fams = {}
            for r in sub:
                fams.setdefault(r["family"], []).append(r["cover_block"])
            print("DEPTH|family_cover|" + lang + "|" + json.dumps({k: round(statistics.mean(v), 2) for k, v in fams.items()}))

        # static facts that bound the answers
        try:
            import yaml  # type: ignore

            cat = yaml.safe_load(open("backend/config/i8/plan_catalog_v1.yaml", encoding="utf-8"))
            meals = cat.get("meals") or []
            slots = {}
            for m in meals:
                for s in m.get("slots") or []:
                    slots[s] = slots.get(s, 0) + 1
            ex = cat.get("exercises") or []
            print("DEPTH|plan_catalog|" + json.dumps({"meals": len(meals), "per_slot": slots, "exercises": len(ex),
                                                       "condition_specific_keys": [k for k in cat if "condition" in k or "diet" in k]}))
        except Exception as e:
            print("DEPTH|plan_catalog|unavailable " + type(e).__name__)
        print("DEPTH|flags|" + json.dumps({
            "attachments_enabled": os.environ.get("SEDI_ATTACHMENTS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
            "memory_llm_extraction": os.environ.get("SEDI_MEMORY_LLM_EXTRACTION_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
            "plan_voice_llm": os.environ.get("SEDI_PLAN_VOICE_LLM", "").strip().lower() in ("1", "true", "yes", "on"),
            "kb_embeddings": os.environ.get("SEDI_KB_EMBEDDINGS_ENABLED", "").strip().lower() in ("1", "true", "yes", "on"),
        }))
        print("DEPTH|chat_caps|" + json.dumps({"limit": CHAT_LIMIT, "block_chars": CHAT_BLOCK_CHARS}))
        print("DEPTH|done|PASS")
    finally:
        db.rollback()
        db.close()


main()
