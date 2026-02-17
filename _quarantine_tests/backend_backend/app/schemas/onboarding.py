from pydantic import BaseModel, Field

class OnboardingRequest(BaseModel):
    """Onboarding request schema - name is REQUIRED"""
    password: str = Field(..., min_length=6, description="User security password (minimum 6 characters)")
    language: str = Field(default="fa", description="Preferred language (default: 'fa')")
    name: str = Field(..., min_length=1, description="User name (REQUIRED, non-empty)")

