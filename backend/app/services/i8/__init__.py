"""I8 Nutrition / Meal Plan — ephemeral fail-closed slice. No new schema."""

from backend.app.services.i8.nutrition_planner import NutritionPlanResult, plan_nutrition

__all__ = ["NutritionPlanResult", "plan_nutrition"]
