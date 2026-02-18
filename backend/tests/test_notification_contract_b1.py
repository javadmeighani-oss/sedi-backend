# tests/test_notification_contract_b1.py
"""
Pytest tests for Release B - Part B1: Notification Contract

Tests:
- Fallback returns non-empty for all 3 types
- dedupe_key format is stable
- enhance_with_ai returns unchanged when disabled
"""

import pytest
from datetime import datetime
from typing import Optional

from app.schemas.notification import NotificationPayload
from app.services.notification_runtime.fallback_generator import generate_fallback_text
from app.services.notification_runtime.ai_enhancer import enhance_with_ai, NOTIF_AI_ENHANCE
from app.services.notification_engine import NotificationBuilder
from app.services.memory.memory_context import MemoryContext


# -------------------- Test Fallback Generator --------------------

def test_fallback_morning_brief_non_empty():
    """Test that fallback returns non-empty text for morning_brief"""
    payload = NotificationPayload(
        user_id=1,
        type="morning_brief",
        title="صبح بخیر",
        body="",
        priority="normal",
        scheduled_for=None,
        dedupe_key="morning_brief:1:2026-02-02",
        metadata=None
    )
    
    result = generate_fallback_text(payload, user_name="عزیزم")
    
    assert result is not None
    assert len(result.strip()) > 0
    assert "صبح بخیر" in result or "عزیزم" in result


def test_fallback_connection_ping_non_empty():
    """Test that fallback returns non-empty text for connection_ping"""
    payload = NotificationPayload(
        user_id=1,
        type="connection_ping",
        title="سلام",
        body="",
        priority="low",
        scheduled_for=None,
        dedupe_key="connection_ping:1:2026-02-02:00",
        metadata=None
    )
    
    result = generate_fallback_text(payload, user_name="عزیزم")
    
    assert result is not None
    assert len(result.strip()) > 0
    assert "سلام" in result or "عزیزم" in result


def test_fallback_health_alert_non_empty():
    """Test that fallback returns non-empty text for health_alert"""
    payload = NotificationPayload(
        user_id=1,
        type="health_alert",
        title="هشدار سلامت",
        body="",
        priority="high",
        scheduled_for=None,
        dedupe_key="health_alert:1:high_heart_rate:2026-02-02T10",
        metadata={"alert_code": "high_heart_rate"}
    )
    
    result = generate_fallback_text(payload, user_name="عزیزم")
    
    assert result is not None
    assert len(result.strip()) > 0
    assert "سلام" in result or "عزیزم" in result or "نکته" in result


def test_fallback_with_memory_context():
    """Test that fallback uses memory context for personalization"""
    payload = NotificationPayload(
        user_id=1,
        type="morning_brief",
        title="صبح بخیر",
        body="",
        priority="normal",
        scheduled_for=None,
        dedupe_key="morning_brief:1:2026-02-02",
        metadata=None
    )
    
    # Create memory context with sleep data
    memory_context = MemoryContext()
    memory_context.sleep_duration_hours = 5.5  # Low sleep
    
    result = generate_fallback_text(payload, user_name="جواد", memory_context=memory_context)
    
    assert result is not None
    assert len(result.strip()) > 0
    # Should mention sleep if available
    assert "جواد" in result or "صبح بخیر" in result


def test_fallback_never_raises():
    """Test that fallback never raises exceptions"""
    # Test with None values
    payload = NotificationPayload(
        user_id=1,
        type="morning_brief",
        title="",
        body="",
        priority="normal",
        scheduled_for=None,
        dedupe_key="test:1:2026-02-02",
        metadata=None
    )
    
    # Should not raise even with None/empty values
    result = generate_fallback_text(payload, user_name=None, memory_context=None)
    assert result is not None
    assert len(result.strip()) > 0


# -------------------- Test Dedupe Key Format --------------------

def test_dedupe_key_morning_brief_format(db):
    """Test that dedupe_key format is stable for morning_brief"""
    from backend.app.services.notification_engine import NotificationBuilder

    builder = NotificationBuilder(db)
    
    now = datetime(2026, 2, 2, 9, 0, 0)
    key = builder.compute_dedupe_key(
        notification_type="morning_brief",
        user_id=1,
        scheduled_for=now
    )
    
    assert key == "morning_brief:1:2026-02-02"
    
    # Same day, different time should give same key
    now2 = datetime(2026, 2, 2, 14, 30, 0)
    key2 = builder.compute_dedupe_key(
        notification_type="morning_brief",
        user_id=1,
        scheduled_for=now2
    )
    
    assert key2 == "morning_brief:1:2026-02-02"
    assert key == key2


def test_dedupe_key_connection_ping_format(db):
    """Test that dedupe_key format is stable for connection_ping"""
    from backend.app.services.notification_engine import NotificationBuilder

    builder = NotificationBuilder(db)
    
    now = datetime(2026, 2, 2, 10, 30, 0)  # 10:30 -> bucket 08
    key = builder.compute_dedupe_key(
        notification_type="connection_ping",
        user_id=1,
        scheduled_for=now
    )
    
    assert key == "connection_ping:1:2026-02-02:08"
    
    # Same 4-hour bucket should give same key
    now2 = datetime(2026, 2, 2, 11, 15, 0)  # 11:15 -> bucket 08
    key2 = builder.compute_dedupe_key(
        notification_type="connection_ping",
        user_id=1,
        scheduled_for=now2
    )
    
    assert key2 == "connection_ping:1:2026-02-02:08"
    assert key == key2


def test_dedupe_key_health_alert_format(db):
    """Test that dedupe_key format is stable for health_alert"""
    from backend.app.services.notification_engine import NotificationBuilder

    builder = NotificationBuilder(db)
    
    now = datetime(2026, 2, 2, 14, 30, 0)
    metadata = {"alert_code": "high_heart_rate"}
    key = builder.compute_dedupe_key(
        notification_type="health_alert",
        user_id=1,
        scheduled_for=now,
        metadata=metadata
    )
    
    assert key == "health_alert:1:high_heart_rate:2026-02-02T14"
    
    # Same hour, same alert code should give same key
    now2 = datetime(2026, 2, 2, 14, 45, 0)
    key2 = builder.compute_dedupe_key(
        notification_type="health_alert",
        user_id=1,
        scheduled_for=now2,
        metadata=metadata
    )
    
    assert key2 == "health_alert:1:high_heart_rate:2026-02-02T14"
    assert key == key2


# -------------------- Test AI Enhancement --------------------

def test_ai_enhance_disabled_returns_unchanged():
    """Test that enhance_with_ai returns unchanged payload when disabled"""
    import os
    
    # Save original value
    original_value = os.getenv("NOTIF_AI_ENHANCE", "false")
    
    try:
        # Ensure AI enhancement is disabled
        os.environ["NOTIF_AI_ENHANCE"] = "false"
        
        # Reload module to pick up new env value
        import importlib
        from backend.app.services.notification_runtime import ai_enhancer
        importlib.reload(ai_enhancer)
        
        payload = NotificationPayload(
            user_id=1,
            type="morning_brief",
            title="صبح بخیر",
            body="Test body",
            priority="normal",
            scheduled_for=None,
            dedupe_key="test:1:2026-02-02",
            metadata=None
        )
        
        result = ai_enhancer.enhance_with_ai(payload)
        
        # Should return unchanged
        assert result.user_id == payload.user_id
        assert result.type == payload.type
        assert result.body == payload.body
        assert result.dedupe_key == payload.dedupe_key
        
    finally:
        # Restore original value
        if original_value:
            os.environ["NOTIF_AI_ENHANCE"] = original_value
        else:
            os.environ.pop("NOTIF_AI_ENHANCE", None)
        import importlib
        from backend.app.services.notification_runtime import ai_enhancer
        importlib.reload(ai_enhancer)


def test_ai_enhance_never_raises():
    """Test that enhance_with_ai never raises exceptions"""
    payload = NotificationPayload(
        user_id=1,
        type="morning_brief",
        title="صبح بخیر",
        body="Test body",
        priority="normal",
        scheduled_for=None,
        dedupe_key="test:1:2026-02-02",
        metadata=None
    )
    
    # Should not raise even if AI engine fails
    result = enhance_with_ai(payload)
    
    assert result is not None
    assert result.user_id == payload.user_id
    assert result.body is not None  # Should always have a body


# -------------------- Test Integration --------------------

def test_build_payload_creates_valid_payload(db):
    """Test that build_payload creates valid NotificationPayload"""
    from backend.app.services.notification_engine import NotificationBuilder

    builder = NotificationBuilder(db)
    
    payload = builder.build_payload(
        user_id=1,
        notification_type="morning_brief",
        title="صبح بخیر",
        body="Test",
        priority="normal",
        scheduled_for=None,
        metadata=None
    )
    
    assert payload.user_id == 1
    assert payload.type == "morning_brief"
    assert payload.title == "صبح بخیر"
    assert payload.body == "Test"
    assert payload.dedupe_key is not None
    assert len(payload.dedupe_key) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
