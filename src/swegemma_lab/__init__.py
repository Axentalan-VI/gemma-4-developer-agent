"""Local lab for the Gemma 4 Developer Agent competition.

Authoring, validation and statistics run here on CPU. Everything that needs the
31B model runs on Kaggle; see notebooks/ and kernels/.
"""

from __future__ import annotations

__all__ = ["build", "validate"]
