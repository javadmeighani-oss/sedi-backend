# app/routers/interact.py
from fastapi import APIRouter, HTTPException, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import User, Memory
from app.core.gpt_engine import ask_sedi
from app.schemas import InteractionResponse
from datetime import datetime
from fastapi import Depends

router = APIRouter()

# ---------------- Introduce User ----------------
@router.post("/introduce", response_model=InteractionResponse)
def introduce_user(
    name: str = Query(...),
    secret_key: str = Query(...),
    lang: str = Query("en"),
    db: Session = Depends(get_db)
):
    existing_user = db.query(User).filter(User.name == name).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="User already exists")

    new_user = User(name=name, secret_key=secret_key, preferred_language=lang)
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    message = {
        "en": f"Hello {name}! I'm Sedi, your intelligent health companion 🌿",
        "fa": f"سلام {name}! من صدی هستم، همراه هوشمند مراقبت سلامتت 🌿",
        "ar": f"مرحباً {name}! أنا سدي، رفيقك الذكي للعناية بالصحة 🌿"
    }

    return InteractionResponse(
        message=message.get(lang, message["en"]),
        language=lang,
        user_id=new_user.id,
        timestamp=datetime.utcnow()
    )


# ---------------- Chat with Sedi ----------------
@router.post("/chat", response_model=InteractionResponse)
def chat_with_sedi(
    name: str = Query(...),
    secret_key: str = Query(...),
    message: str = Query(...),
    lang: str = Query("en"),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.name == name,
        User.secret_key == secret_key
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not recognized")

    sedi_reply = ask_sedi(message, language=lang)

    memory = Memory(
        user_id=user.id,
        user_message=message,
        sedi_response=sedi_reply,
        language=lang
    )
    db.add(memory)
    db.commit()

    return InteractionResponse(
        message=sedi_reply,
        language=lang,
        user_id=user.id,
        timestamp=datetime.utcnow()
    )
# ------------------ Memory History ------------------
@router.get("/history")
def get_user_history(
    name: str = Query(...),
    secret_key: str = Query(...),
    db: Session = Depends(get_db)
):
    """
    دریافت تاریخچه گفتگوهای کاربر با صدی
    """
    user = db.query(User).filter(
        User.name == name,
        User.secret_key == secret_key
    ).first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    history = db.query(Memory).filter(Memory.user_id == user.id).all()

    if not history:
        return {"message": "No conversations found for this user."}

    return [
        {
            "user_message": h.user_message,
            "sedi_response": h.sedi_response,
            "language": h.language,
            "timestamp": h.created_at
        }
        for h in history
    ]
