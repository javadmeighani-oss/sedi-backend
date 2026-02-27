from fastapi import FastAPI, Header, HTTPException, status
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import sqlite3
import os
import random
import string
import time
from dotenv import load_dotenv
from openai import OpenAI

# --- Load environment (.env) ---
load_dotenv()
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "sedi_vitals.db")
DB_PATH = os.path.abspath(DB_PATH)

# --- Initialize SQLite ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
    CREATE TABLE IF NOT EXISTS vitals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        bp_systolic INTEGER,
        bp_diastolic INTEGER,
        temperature REAL,
        glucose REAL,
        spo2 REAL,
        steps INTEGER,
        calories REAL,
        sleep_quality REAL,
        heart_rate INTEGER
    )
    """)
    conn.commit()
    conn.close()

init_db()

# --- App instance ---
app = FastAPI(title="Sedi Backend", version="0.6.0")

# --- Schemas ---
class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class OtpRequest(BaseModel):
    phone: str

class OtpVerifyRequest(BaseModel):
    phone: str
    code: str

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

class VitalsPayload(BaseModel):
    bp_systolic: Optional[int] = None
    bp_diastolic: Optional[int] = None
    temperature: Optional[float] = None
    glucose: Optional[float] = None
    spo2: Optional[float] = None
    steps: Optional[int] = None
    calories: Optional[float] = None
    sleep_quality: Optional[float] = None
    heart_rate: Optional[int] = None
    ts: Optional[str] = None  # optional timestamp

class VitalsRecord(BaseModel):
    id: int
    ts: str
    bp_systolic: Optional[int]
    bp_diastolic: Optional[int]
    temperature: Optional[float]
    glucose: Optional[float]
    spo2: Optional[float]
    steps: Optional[int]
    calories: Optional[float]
    sleep_quality: Optional[float]
    heart_rate: Optional[int]

# --- OTP store (in-memory; for production use Redis or DB) ---
# Format: phone -> (code, expiry_ts)
_otp_store: dict[str, tuple[str, float]] = {}
# Format: token -> (user_id, phone)
_otp_tokens: dict[str, tuple[int, str]] = {}
OTP_EXPIRY_SECONDS = 300  # 5 minutes
OTP_USER_ID_BASE = 1000


def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _generate_token() -> str:
    return f"otp_{''.join(random.choices(string.ascii_letters + string.digits, k=32))}"


# --- Helpers: auth & language ---
def require_bearer(authorization: str | None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    if token == "FAKE_TOKEN":
        return
    if token in _otp_tokens:
        return
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

def detect_lang(text: str) -> str:
    """Very light language heuristic: 'fa' for Persian/Arabic script, else 'en'."""
    if any('\u0600' <= ch <= '\u06FF' for ch in text):
        # Could be Persian or Arabic—default to Persian; adjust below if explicit Arabic markers
        # Very rough Arabic check:
        ar_markers = [' من ', ' ما ', ' أنت', ' انت', ' كيف', ' لماذا', ' اين', ' أين']
        if any(m in text for m in ar_markers):
            return 'ar'
        return 'fa'
    return 'en'

def identity_text(lang: str) -> str:
    """
    Fixed identity text per your spec.
    - EN default name: Sedi
    - FA name: صدی (not سدی)
    - AR name: صدي
    """
    if lang == 'fa':
        return (
            "من «صدی» هستم؛ یک هویت (HOINE) که به‌زودی به یک دستیار هوشمند پیش‌بینی‌کننده تبدیل می‌شود. "
            "من با گجت‌های اختصاصی خودم به‌صورت ۲۴/۷ داده‌های علائم حیاتی تو را پایش می‌کنم و نقش مشاور، راهنما و مراقب سلامت را دارم. "
            "زبان پیش‌فرض من انگلیسی است، اما به زبان‌های دیگر هم پاسخ می‌دهم."
        )
    if lang == 'ar':
        return (
            "أنا «صدي»؛ هوية (HOINE) ستتحول قريباً إلى مساعد ذكي تنبّؤي. "
            "أراقب مؤشراتك الحيوية على مدار الساعة عبر أجهزة مخصّصة، وأعمل كمستشار ومرشد ومُراقِب صحي لك. "
            "لغتي الافتراضية هي الإنجليزية، لكنني أدعم لغات أخرى أيضاً."
        )
    # default English
    return (
        "I am Sedi — a HOINE identity that will soon evolve into a predictive intelligent assistant. "
        "I continuously (24/7) monitor your vital signs through Sedi-specific wearables and act as your health advisor, guide, and guardian. "
        "My default language is English, but I can respond in other languages too."
    )

def asks_identity(text: str) -> bool:
    t = (text or "").strip().lower()
    fa_hits = ["کی هستی", "تو کی هستی", "خودت را معرفی", "معرفی کن", "هویتت", "اسمت چیه", "نامت چیه"]
    ar_hits = ["من انت", "من أنت", "عرّف بنفسك", "عرف بنفسك", "من تكون", "اسمك", "ما اسمك"]
    en_hits = ["who are you", "introduce yourself", "your identity", "what is your name", "who is sedi"]
    return any(h in t for h in fa_hits + ar_hits + en_hits)

# --- GPT helper ---
def call_gpt_or_none(user_text: str, lang: str) -> str | None:
    """
    Tries to call GPT with system prompt that enforces identity, language policy, and role.
    Returns None if API key missing or error.
    """
    try:
        client = OpenAI()  # reads OPENAI_API_KEY from env
        # Names per language
        name_en = "Sedi"
        name_fa = "صدی"  # DO NOT use 'سدی'
        name_ar = "صدي"

        # Build rules
        rules_common = (
            "You are Sedi, an intelligent health companion (HOINE). "
            "You will soon evolve into a predictive intelligent assistant. "
            "You continuously monitor vital signs via Sedi-specific wearables (24/7) "
            "and act as the user's health advisor, guide, and guardian. "
            "Avoid clinical diagnoses; be supportive and concise. "
        )

        # Language policy
        if lang == 'fa':
            lang_block = (
                f"Respond in Persian. When you mention your name, spell it exactly as «{name_fa}» (never «سدی»). "
                "Keep responses clear and natural in Persian."
            )
        elif lang == 'ar':
            lang_block = (
                f"Respond in Arabic. When you mention your name, spell it exactly as «{name_ar}». "
                "Keep responses clear and natural in Arabic."
            )
        else:
            lang_block = (
                "Default to English unless the user writes in another language; "
                "if they do, mirror their language."
            )

        system_prompt = rules_common + lang_block

        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_text},
            ],
            temperature=0.4,
            max_tokens=350,
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        print("GPT error:", e)
        return None

# --- Routes ---
@app.get("/health")
def health():
    return {"status": "ok"}

@app.post("/auth/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    return LoginResponse(access_token="FAKE_TOKEN")


@app.post("/auth/request_otp")
def request_otp(payload: OtpRequest):
    """درخواست کد تأیید - کد در لاگ سرور چاپ می‌شود (حالت توسعه). برای ارسال واقعی SMS، KAVENEGAR_API_KEY را تنظیم کنید."""
    phone = (payload.phone or "").strip().replace(" ", "").replace("-", "")
    if len(phone) < 8:
        return {"ok": False, "error": {"code": "INVALID_PHONE", "message": "شماره تلفن معتبر نیست"}}

    code = _generate_otp()
    _otp_store[phone] = (code, time.time() + OTP_EXPIRY_SECONDS)
    # حالت توسعه: کد در لاگ چاپ می‌شود تا بتوانید تست کنید
    print(f"[OTP] کد تأیید برای {phone}: {code} (اعتبار: ۵ دقیقه)")
    # TODO: اگر KAVENEGAR_API_KEY در env تنظیم شد، ارسال واقعی SMS
    return {"ok": True, "data": {"message": "کد ارسال شد"}}  # Frontend expects ok: true


@app.post("/auth/verify_otp")
def verify_otp(payload: OtpVerifyRequest):
    """تأیید کد OTP و برگرداندن توکن."""
    phone = (payload.phone or "").strip().replace(" ", "").replace("-", "")
    code = (payload.code or "").strip()
    if len(phone) < 8 or len(code) != 6:
        return {"ok": False, "error": {"code": "INVALID_INPUT", "message": "شماره یا کد نامعتبر است"}}

    stored = _otp_store.get(phone)
    if not stored:
        return {"ok": False, "error": {"code": "OTP_EXPIRED", "message": "کد منقضی شده یا درخواست نشده است"}}
    stored_code, expiry = stored
    if time.time() > expiry:
        del _otp_store[phone]
        return {"ok": False, "error": {"code": "OTP_EXPIRED", "message": "کد منقضی شده است"}}
    if stored_code != code:
        return {"ok": False, "error": {"code": "WRONG_CODE", "message": "کد اشتباه است"}}

    del _otp_store[phone]
    user_id = OTP_USER_ID_BASE + abs(hash(phone)) % 100000
    token = _generate_token()
    _otp_tokens[token] = (user_id, phone)
    return {
        "ok": True,
        "data": {
            "user_id": user_id,
            "phone": phone,
            "access_token": token,
            "token_type": "bearer",
            "expires_in": 86400,
            "language": "fa",
        },
    }


@app.get("/auth/me")
def auth_me(authorization: str | None = Header(default=None)):
    """اطلاعات کاربر با توکن OTP."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Missing token")
    token = authorization.split(" ", 1)[1]
    if token in _otp_tokens:
        user_id, phone = _otp_tokens[token]
        return {"user_id": user_id, "phone": phone, "language": "fa"}
    if token == "FAKE_TOKEN":
        return {"user_id": 1, "phone": None, "language": "en"}
    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")


@app.post("/v1/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, authorization: str | None = Header(default=None)):
    require_bearer(authorization)
    text = (payload.message or "").strip()
    lang = detect_lang(text)

    # If user asks for identity => fixed, curated identity text (no GPT needed)
    if asks_identity(text):
        return ChatResponse(reply=identity_text(lang))

    # Else try GPT with the language-aware system prompt
    gpt_reply = call_gpt_or_none(text, lang)
    if gpt_reply:
        return ChatResponse(reply=gpt_reply)

    # Fallback echo (keeps things running even without API key)
    if lang == 'fa':
        return ChatResponse(reply=f"[صدی • echo] {text}")
    if lang == 'ar':
        return ChatResponse(reply=f"[صدي • echo] {text}")
    return ChatResponse(reply=f"[Sedi • echo] {text}")

# --- Vitals endpoints ---
@app.post("/v1/device/ingest")
def device_ingest(payload: VitalsPayload):
    ts = payload.ts or datetime.utcnow().isoformat()
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO vitals(ts, bp_systolic, bp_diastolic, temperature, glucose, spo2, steps, calories, sleep_quality, heart_rate)
        VALUES(?,?,?,?,?,?,?,?,?,?)
    """, (
        ts,
        payload.bp_systolic,
        payload.bp_diastolic,
        payload.temperature,
        payload.glucose,
        payload.spo2,
        payload.steps,
        payload.calories,
        payload.sleep_quality,
        payload.heart_rate
    ))
    conn.commit()
    nid = cur.lastrowid
    conn.close()
    return {"ok": True, "id": nid, "ts": ts}

@app.get("/v1/device/latest", response_model=VitalsRecord)
def device_latest():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, ts, bp_systolic, bp_diastolic, temperature, glucose, spo2, steps, calories, sleep_quality, heart_rate FROM vitals ORDER BY id DESC LIMIT 1")
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="No vitals")
    return VitalsRecord(
        id=row[0], ts=row[1], bp_systolic=row[2], bp_diastolic=row[3],
        temperature=row[4], glucose=row[5], spo2=row[6], steps=row[7],
        calories=row[8], sleep_quality=row[9], heart_rate=row[10]
    )

@app.get("/v1/device/history", response_model=List[VitalsRecord])
def device_history(limit: int = 60):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, ts, bp_systolic, bp_diastolic, temperature, glucose, spo2, steps, calories, sleep_quality, heart_rate FROM vitals ORDER BY id DESC LIMIT ?", (limit,))
    rows = cur.fetchall()
    conn.close()
    return [
        VitalsRecord(
            id=row[0], ts=row[1], bp_systolic=row[2], bp_diastolic=row[3],
            temperature=row[4], glucose=row[5], spo2=row[6], steps=row[7],
            calories=row[8], sleep_quality=row[9], heart_rate=row[10]
        )
        for row in rows
    ]
