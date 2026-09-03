"""Convert nested structures to JSON-serializable plain Python types."""

from __future__ import annotations

import math
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

try:
    import numpy as np
except Exception:  # pragma: no cover
    np = None  # type: ignore

try:
    import pandas as pd
except Exception:  # pragma: no cover
    pd = None  # type: ignore


def json_safe(obj: Any) -> Any:
    """Recursively normalize values for json.dumps / SQLAlchemy JSON columns."""
    if obj is None:
        return None
    if np is not None and isinstance(obj, np.generic):
        try:
            return json_safe(obj.item())
        except Exception:
            if isinstance(obj, np.floating):
                x = float(obj)
                return None if math.isnan(x) or math.isinf(x) else x
            if isinstance(obj, np.integer):
                return int(obj)
            return str(obj)
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, (bytes, bytearray, memoryview)):
        try:
            return bytes(obj).decode("utf-8", errors="replace")
        except Exception:
            return str(obj)
    if isinstance(obj, (int, float)):
        if isinstance(obj, float) and (math.isnan(obj) or math.isinf(obj)):
            return None
        return obj
    if isinstance(obj, Decimal):
        try:
            return float(obj)
        except Exception:
            return str(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if pd is not None:
        if isinstance(obj, pd.Timestamp):
            return obj.isoformat()
    if isinstance(obj, dict):
        return {str(k): json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set, frozenset)):
        return [json_safe(x) for x in obj]
    return str(obj)
