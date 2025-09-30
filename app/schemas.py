from pydantic import BaseModel, Field
from typing import Optional, Dict
from datetime import datetime

class LoginRequest(BaseModel):
    username: str
    password: str

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

class ChatRequest(BaseModel):
    message: str

class ChatResponse(BaseModel):
    reply: str

class VitalSample(BaseModel):
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    systolic: Optional[int] = None          # فشار خون بالا
    diastolic: Optional[int] = None         # فشار خون پایین
    body_temp_c: Optional[float] = None     # دمای بدن
    glucose_mg_dL: Optional[float] = None   # قند خون
    spo2_pct: Optional[float] = None        # اکسیژن خون
    hr_bpm: Optional[int] = None            # ضربان قلب
    ecg_state: Optional[str] = None         # وضعیت ECG (simple: normal/arrhythmia/unknown)
    steps: Optional[int] = None             # قدم‌شمار
    activity_level: Optional[int] = None    # 0..100
    sleep_quality: Optional[int] = None     # 0..100

class VitalWithStatus(BaseModel):
    sample: VitalSample
    status_by_metric: Dict[str, str]  # normal | warn | danger
