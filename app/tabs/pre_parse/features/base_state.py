from __future__ import annotations

BASE_STATE_ERROR = "error"
BASE_STATE_NORMAL = "normal"

def is_error_base_state(value: object) -> bool:
    return str(value or "").strip().lower() == BASE_STATE_ERROR
