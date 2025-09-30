from fastapi import APIRouter
from app.schemas import LoginRequest, LoginResponse

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/login", response_model=LoginResponse)
def login(payload: LoginRequest):
    # ساده: هر ورودی را می‌پذیریم
    return LoginResponse(access_token="FAKE_TOKEN")
