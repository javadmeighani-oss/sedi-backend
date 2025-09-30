from fastapi import APIRouter, Depends
from collections import deque
from typing import Deque, Optional
from random import randint, uniform, choice
from datetime import datetime
from app.schemas import VitalSample, VitalWithStatus
from app.deps import get_bearer_token

router = APIRouter(prefix="/v1/device", tags=["device"])

# ساده‌ترین روش: حافظه‌ی موقتی (در صورت ریست سرور پاک می‌شود)
BUFFER_MAX = 256
samples: Deque[VitalSample] = deque(maxlen=BUFFER_MAX)

def classify(sample: VitalSample) -> VitalWithStatus:
    status = {}

    # فشار خون
    if sample.systolic is not None and sample.diastolic is not None:
        sys, dia = sample.systolic, sample.diastolic
        if sys < 90 or dia < 60: status["bp"] = "warn"
        elif sys > 140 or dia > 90: status["bp"] = "danger"
        else: status["bp"] = "normal"

    # دمای بدن
    if sample.body_temp_c is not None:
        t = sample.body_temp_c
        if t < 35.5 or t > 38.0: status["temp"] = "danger"
        elif 37.3 <= t <= 38.0 or 35.5 <= t < 36.0: status["temp"] = "warn"
        else: status["temp"] = "normal"

    # قند خون (mg/dL) — غیرناشتا ساده
    if sample.glucose_mg_dL is not None:
        g = sample.glucose_mg_dL
        if g < 70 or g > 240: status["glucose"] = "danger"
        elif 180 < g <= 240 or 70 <= g < 80: status["glucose"] = "warn"
        else: status["glucose"] = "normal"

    # SpO2
    if sample.spo2_pct is not None:
        s = sample.spo2_pct
        if s < 90: status["spo2"] = "danger"
        elif 90 <= s < 95: status["spo2"] = "warn"
        else: status["spo2"] = "normal"

    # ضربان قلب
    if sample.hr_bpm is not None:
        hr = sample.hr_bpm
        if hr < 45 or hr > 130: status["hr"] = "danger"
        elif (45 <= hr < 55) or (100 < hr <= 130): status["hr"] = "warn"
        else: status["hr"] = "normal"

    # ECG (نمادین)
    if sample.ecg_state:
        status["ecg"] = "danger" if sample.ecg_state == "arrhythmia" else "normal"

    # فعالیت/خواب (اطلاع‌رسانی نرم)
    if sample.activity_level is not None:
        status["activity"] = "normal"  # اطلاع‌رسانی
    if sample.sleep_quality is not None:
        status["sleep"] = "normal"     # اطلاع‌رسانی

    return VitalWithStatus(sample=sample, status_by_metric=status)

@router.post("/ingest", response_model=VitalWithStatus)
def ingest(sample: VitalSample, token: str = Depends(get_bearer_token)):
    samples.append(sample)
    return classify(sample)

@router.get("/latest", response_model=Optional[VitalWithStatus])
def latest(token: str = Depends(get_bearer_token)):
    if not samples:
        return None
    return classify(samples[-1])

# برای تست سریع: تولید فیک (اختیاری—اگر خواستی از اپ هم می‌توانی بزنی)
@router.post("/fake_tick", response_model=VitalWithStatus)
def fake_tick(token: str = Depends(get_bearer_token)):
    sample = VitalSample(
        timestamp=datetime.utcnow(),
        systolic=randint(100, 160),
        diastolic=randint(60, 100),
        body_temp_c=round(uniform(36.0, 38.5), 1),
        glucose_mg_dL=round(uniform(80, 250), 0),
        spo2_pct=round(uniform(88, 99), 0),
        hr_bpm=randint(48, 140),
        ecg_state=choice(["normal", "normal", "arrhythmia"]),
        steps=randint(0, 500),
        activity_level=randint(0, 100),
        sleep_quality=randint(40, 95),
    )
    samples.append(sample)
    return classify(sample)
