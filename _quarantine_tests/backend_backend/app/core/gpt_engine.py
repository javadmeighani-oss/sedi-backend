# app/core/gpt_engine.py
import os
from openai import OpenAI
from dotenv import load_dotenv

# Load API key from .env file
load_dotenv()

# No need to pass api_key to constructor - it reads from env automatically
client = OpenAI()


def ask_sedi(prompt: str, language: str = "en") -> str:
    """
    Connect to GPT to generate natural Sedi responses (compatible with new SDK version)
    """
    try:
        base_prompt = {
            "en": "You are Sedi, an empathetic AI health assistant who speaks with warmth and care.",
            "fa": "تو صدی هستی، یک دستیار سلامت باهوش و مهربان که با آرامش و همدلی صحبت می‌کند.",
            "ar": "أنت صدي، مساعد صحي ذكي يتحدث بلطف واهتمام."
        }

        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": base_prompt.get(language, base_prompt["en"])},
                {"role": "user", "content": prompt}
            ],
            temperature=0.7,
            max_tokens=200,
        )

        return completion.choices[0].message.content.strip()

    except Exception as e:
        print(f"[GPT ERROR] {e}")
        fallback = {
            "en": "Sorry, I couldn't connect to my thinking cloud right now.",
            "fa": "متاسفم، الان به سرور پردازش متصل نیستم.",
            "ar": "عذرًا، لا أستطيع الاتصال بالسحابة الآن."
        }
        return fallback.get(language, fallback["en"])
