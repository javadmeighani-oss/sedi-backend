"""I5-KNOW-05 — governed weekly knowledge acquisition (rehearsal; Production weekly OFF).

Keep this package __init__ free of heavy imports that create cycles with know04.live_canaries.
"""

from backend.app.services.i5.know05.modes import Know05Mode, assert_mode_authorized, production_activation_flags
from backend.app.services.i5.know05.ncbi_identity import load_ncbi_operational_identity

__all__ = [
    "Know05Mode",
    "assert_mode_authorized",
    "production_activation_flags",
    "load_ncbi_operational_identity",
]
