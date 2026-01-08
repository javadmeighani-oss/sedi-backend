from pydantic import BaseModel, Field

class OnboardingRequest(BaseModel):
    """Onboarding request schema - name is REQUIRED, password removed"""
    name: str = Field(..., min_length=1, description="User name (REQUIRED, non-empty)")

