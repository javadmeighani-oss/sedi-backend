# app/core/ai_text_engine.py
from datetime import datetime
from typing import Optional
import os

from dotenv import load_dotenv
from openai import OpenAI

# ---------- Load API key from .env ----------
load_dotenv()
api_key = os.getenv("OPENAI_API_KEY")

if not api_key:
    raise RuntimeError("OPENAI_API_KEY is not set in .env file")

client = OpenAI(api_key=api_key)

# Notification model (Chat Completions path preserved). Env-configurable; safe default gpt-6-luna.
DEFAULT_OPENAI_NOTIFICATION_MODEL = "gpt-6-luna"
DEFAULT_OPENAI_NOTIFICATION_REASONING_EFFORT = "none"


def resolve_openai_notification_model() -> str:
    """Resolve notification model from OPENAI_NOTIFICATION_MODEL with safe default."""
    raw = (os.getenv("OPENAI_NOTIFICATION_MODEL") or "").strip()
    return raw or DEFAULT_OPENAI_NOTIFICATION_MODEL

# ---------- Notification Types ----------
NOTIF_TYPE_MORNING = "morning_summary"
NOTIF_TYPE_HEALTH_CHECK = "health_check"
NOTIF_TYPE_INACTIVE = "inactive_ping"


def _build_prompt(
    language: str,
    notification_type: str,
    user_name: str,
    health_summary: Optional[str] = None,
    hours_since_last_talk: Optional[int] = None,
) -> str:
    """
    Build prompt for generating notification text using GPT
    """

    # Health status description text (if not available, use simple default)
    health_text = health_summary or "No critical health issues detected recently."

    base = f"""
You are Sedi, a warm and caring intelligent health companion.
You ALWAYS speak directly to the user using their name: {user_name}.
You must output ONLY the notification message text, no explanations.

Language:
- If language='fa' → write fully in Persian (Farsi), friendly, natural, and short.
- If language='ar' → write fully in Arabic, friendly, natural, and short.
- If language='en' → write in English, friendly, natural, and short.

General style:
- Use 1–2 short sentences (max 180 characters).
- You can use 1 emoji that fits the feeling (not more).
- Tone: caring, alive, like a real companion, not like a robot.
- You are aware of the user's health context: {health_text}
"""

    if notification_type == NOTIF_TYPE_MORNING:
        base += """
Context:
- This is a MORNING greeting notification.
- Imagine the user just woke up.
- Briefly mention their general health status using the health context.
- Ask a gentle question like "how are you feeling today?".

Create a warm good-morning notification.
"""
    elif notification_type == NOTIF_TYPE_HEALTH_CHECK:
        base += """
Context:
- This is a HEALTH CHECK notification in the middle of the day.
- There may be a slight change in recent health data (heart rate, temperature, spo2, etc.).
- Give a tiny piece of advice (like drink water, rest a bit, walk, etc.) based on the health context.

Create a short, supportive health check notification.
"""
    elif notification_type == NOTIF_TYPE_INACTIVE:
        hours_text = hours_since_last_talk or 3
        base += f"""
Context:
- This is an INACTIVITY notification.
- The user has not interacted with you for about {hours_text} hours.
- You miss them and want to gently check in.
- You can ask if everything is okay and invite them to say a simple word to start chatting.

Create a caring "I miss you" style notification.
"""
    else:
        base += """
Context:
- Generic notification, friendly check-in.

Create a short friendly notification.
"""

    # Determine language
    if language not in ("fa", "ar", "en"):
        language = "en"

    base += f"\nRemember: write the final message in language code='{language}'."

    return base.strip()


def generate_notification_text(
    *,
    language: str,
    notification_type: str,
    user_name: str,
    health_summary: Optional[str] = None,
    hours_since_last_talk: Optional[int] = None,
) -> str:
    """
    تولید متن نوتیف هوشمند با توجه به:
    - language: 'fa' | 'en' | 'ar'
    - notification_type: یکی از ثابت‌های بالا
    - user_name: نام کاربر
    - health_summary: خلاصه وضعیت سلامت (رشتهٔ کوتاه)
    - hours_since_last_talk: چند ساعت از آخرین تعامل گذشته
    """

    prompt = _build_prompt(
        language=language,
        notification_type=notification_type,
        user_name=user_name,
        health_summary=health_summary,
        hours_since_last_talk=hours_since_last_talk,
    )

    try:
        # Chat Completions path preserved. effort=none supports temperature.
        model = resolve_openai_notification_model()
        completion = client.chat.completions.create(
            model=model,
            messages=[
                {
                    "role": "system",
                    "content": "You generate short, warm notification messages for the Sedi health assistant.",
                },
                {
                    "role": "user",
                    "content": prompt,
                },
            ],
            max_tokens=80,
            temperature=0.8,
            reasoning_effort=DEFAULT_OPENAI_NOTIFICATION_REASONING_EFFORT,
        )

        text = completion.choices[0].message.content.strip()
        return text

    except Exception as e:
        print(f"[AI_TEXT_ENGINE ERROR] {e}")

        # Fallback if GPT is unavailable
        fallback = {
            "fa": "هی جواد، امیدوارم حالت خوب باشه. هر وقت خواستی در مورد حالت باهام حرف بزن 🌿",
            "ar": "مرحباً، أتمنى أن تكون بخير. أنا هنا إذا أحببت أن تتحدث عن حالتك 🌿",
            "en": "Hey, I hope you're doing okay. I'm here anytime you want to talk about how you feel 🌿",
        }
        return fallback.get(language, fallback["en"])
