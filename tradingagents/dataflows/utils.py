import os
import json
import re
import pandas as pd
from datetime import date, timedelta, datetime
from typing import Annotated

SavePathType = Annotated[str, "File path to save data. If None, data is not saved."]

_UNSAFE_TICKER_PATTERN = re.compile(r"\.\.|[/\\]|[\x00-\x1f]")


def safe_ticker_component(ticker: str) -> str:
    """Sanitize ticker for filesystem paths and checkpoint thread IDs."""
    raw = (ticker or "").strip()
    if not raw or _UNSAFE_TICKER_PATTERN.search(raw):
        raise ValueError(f"Invalid ticker for path component: {ticker!r}")
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", raw)
    return safe or "unknown"

def save_output(data: pd.DataFrame, tag: str, save_path: SavePathType = None) -> None:
    if save_path:
        data.to_csv(save_path)
        print(f"{tag} saved to {save_path}")


def get_current_date():
    return date.today().strftime("%Y-%m-%d")


def decorate_all_methods(decorator):
    def class_decorator(cls):
        for attr_name, attr_value in cls.__dict__.items():
            if callable(attr_value):
                setattr(cls, attr_name, decorator(attr_value))
        return cls

    return class_decorator


def get_next_weekday(date):

    if not isinstance(date, datetime):
        date = datetime.strptime(date, "%Y-%m-%d")

    if date.weekday() >= 5:
        days_to_add = 7 - date.weekday()
        next_weekday = date + timedelta(days=days_to_add)
        return next_weekday
    else:
        return date
