"""Pure, dependency-free domain logic for TrialSync."""

from .comparison import compare_facts
from .impact import assess_impact

__all__ = ["compare_facts", "assess_impact"]
