"""Five-tier rating shared vocabulary."""

from __future__ import annotations

import json
import re
from enum import Enum
from typing import Optional

RATINGS_5_TIER = ("Buy", "Overweight", "Hold", "Underweight", "Sell")

_RATING_ALIASES = {
    "buy": "Buy",
    "强力买入": "Buy",
    "overweight": "Overweight",
    "增持": "Overweight",
    "hold": "Hold",
    "持有": "Hold",
    "underweight": "Underweight",
    "减持": "Underweight",
    "sell": "Sell",
    "卖出": "Sell",
}

_THREE_TIER_FROM_FIVE = {
    "Buy": "BUY",
    "Overweight": "BUY",
    "Hold": "HOLD",
    "Underweight": "SELL",
    "Sell": "SELL",
}


class PortfolioRating(str, Enum):
    BUY = "Buy"
    OVERWEIGHT = "Overweight"
    HOLD = "Hold"
    UNDERWEIGHT = "Underweight"
    SELL = "Sell"


def parse_rating(text: str) -> Optional[str]:
    if not text:
        return None
    normalized = text.strip()
    for tier in RATINGS_5_TIER:
        if tier.lower() in normalized.lower():
            return tier
    key = normalized.lower().replace(" ", "")
    return _RATING_ALIASES.get(key)


def map_five_to_three(rating: str) -> str:
    return _THREE_TIER_FROM_FIVE.get(rating, "HOLD")


_VERDICT_RE = re.compile(r"<!--\s*VERDICT:\s*(\{.*?\})\s*-->", re.IGNORECASE | re.DOTALL)
_FIVE_TIER_LINE_RE = re.compile(
    r"五档评级[：:]\s*(" + "|".join(RATINGS_5_TIER) + r"|买入|增持|持有|减持|卖出)",
    re.IGNORECASE,
)


def infer_rating_5tier(
    *,
    direction: Optional[str] = None,
    confidence: Optional[int] = None,
    decision: Optional[str] = None,
) -> str:
    """Map coarse direction/decision + confidence to a five-tier label."""
    conf = 50 if confidence is None else max(0, min(100, int(confidence)))
    d = (direction or "").strip()
    dec = (decision or "").strip().upper()

    bearish = dec == "SELL" or any(k in d for k in ("偏空", "看空", "BEARISH", "LEAN_BEARISH"))
    bullish = dec == "BUY" or any(k in d for k in ("偏多", "看多", "BULLISH", "LEAN_BULLISH"))

    if bearish:
        return "Sell" if conf >= 70 else "Underweight"
    if bullish:
        return "Buy" if conf >= 80 else "Overweight"
    if dec == "HOLD" or "中性" in d or "NEUTRAL" in d.upper():
        return "Hold"
    return "Hold"


def extract_rating_5tier_from_text(
    text: Optional[str],
    *,
    direction: Optional[str] = None,
    confidence: Optional[int] = None,
    decision: Optional[str] = None,
) -> Optional[str]:
    """Parse explicit five-tier rating from VERDICT/正文，否则按方向推断。"""
    if text:
        match = _VERDICT_RE.search(text)
        if match:
            try:
                raw = match.group(1).strip().replace("\n", " ").replace("\r", " ")
                payload = json.loads(raw)
                explicit = payload.get("rating_5tier") or payload.get("rating")
                parsed = parse_rating(str(explicit)) if explicit else None
                if parsed:
                    return parsed
            except (json.JSONDecodeError, TypeError, ValueError):
                pass

        line_match = _FIVE_TIER_LINE_RE.search(text)
        if line_match:
            parsed = parse_rating(line_match.group(1))
            if parsed:
                return parsed

        for tier in RATINGS_5_TIER:
            if re.search(rf"\b{re.escape(tier)}\b", text):
                return tier

    if direction or decision or confidence is not None:
        return infer_rating_5tier(direction=direction, confidence=confidence, decision=decision)
    return None
