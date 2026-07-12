"""Research Profile module.

Provides loading, validation, and typed dataclasses for user-defined
investment research preferences.
"""

from .models import Exclusions, Presentation, Processing, Profile, Research
from .loader import load_profile

__all__ = [
    "load_profile",
    "Profile",
    "Research",
    "Presentation",
    "Processing",
    "Exclusions",
]
