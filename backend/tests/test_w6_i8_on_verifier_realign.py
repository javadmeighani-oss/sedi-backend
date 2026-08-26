"""Static bounds for W6 I8=ON verifier realign (no network)."""
from pathlib import Path

WF = Path(__file__).resolve().parents[2] / ".github/workflows/w6p01-prod-readonly-preflight.yml"


def test_w6_preflight_requires_i8_on():
    text = WF.read_text(encoding="utf-8")
    assert "must be ON" in text
    assert "must be OFF" not in text
    assert "I8=ON expected" in text
    assert "flag must remain OFF" not in text
    assert "exit 22" not in text
    assert 'I8_EFFECTIVE}" != "ON"' in text
