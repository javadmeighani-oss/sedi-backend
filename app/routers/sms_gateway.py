# app/routers/sms_gateway.py
from fastapi import APIRouter, Depends, Request
from datetime import datetime
from app.schemas import APIResponse, ErrorInfo

router = APIRouter()

# حافظه ساده برای ثبت لاگ پیام‌ها
sent_messages = []


@router.post("/send", response_model=APIResponse)
async def send_sms(request: Request):
    """
    ارسال پیامک داخلی از سرور صدی
    {
      "to": "+989121234567",
      "message": "Your verification code is 1234."
    }
    """
    data = await request.json()
    to = data.get("to")
    message = data.get("message")

    if not to or not message:
        return APIResponse(ok=False, error=ErrorInfo(code="INVALID_INPUT", message="Phone or message missing."))

    # در این نسخه آزمایشی پیام را فقط لاگ می‌کنیم (در آینده اتصال GSM یا اپراتور)
    log = {
        "to": to,
        "message": message,
        "status": "queued",
        "time": datetime.utcnow().isoformat()
    }
    sent_messages.append(log)
    print(f"[Sedi-SMS] → {to}: {message}")

    # پاسخ شبیه به سرویس واقعی
    return APIResponse(ok=True, data={"sent": True, "to": to, "time": log["time"]})


@router.get("/logs", response_model=APIResponse)
async def get_sms_logs():
    """
    مشاهده آخرین پیام‌های ارسال‌شده (برای تست)
    """
    return APIResponse(ok=True, data={"messages": sent_messages[-10:]})
