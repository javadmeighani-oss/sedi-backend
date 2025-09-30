from fastapi import APIRouter, Depends
from app.schemas import ChatRequest, ChatResponse
from app.deps import get_bearer_token

router = APIRouter(prefix="/v1", tags=["chat"])

@router.post("/chat", response_model=ChatResponse)
def chat(payload: ChatRequest, token: str = Depends(get_bearer_token)):
    # فعلاً حالت echo. بعداً اتصال GPT.
    text = payload.message.strip()
    return ChatResponse(reply=f"[Sedi • echo] {text}")
