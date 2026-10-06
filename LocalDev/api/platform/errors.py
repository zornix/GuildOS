"""Turn an internal exception into a fixed, user-safe message. The original goes to the log."""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def public_message(exc: Exception, known: dict[str, str], default: str) -> str:
    """`known` maps a regex (searched in str(exc)) to the fixed text to show.

    First match wins. Every call logs the original text, mapped or not.
    """
    text = str(exc)
    message = next((m for pattern, m in known.items() if re.search(pattern, text)), default)
    logger.warning("error surfaced as %r: %s", message, text)
    return message
