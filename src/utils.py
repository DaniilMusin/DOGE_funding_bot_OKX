from __future__ import annotations

def safe_float(value: str | float | int | None, default: float = 0.0) -> float:
    """Safely convert value to float.

    Returns ``default`` if the conversion fails or value is blank.
    """
    if value in (None, ""):
        return default
    try:
        return float(value)
    except (ValueError, TypeError):
        return default
