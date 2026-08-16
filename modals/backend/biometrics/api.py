from __future__ import annotations

from rest_framework.views import exception_handler


def _flatten_error_detail(detail) -> str:
    if isinstance(detail, dict):
        messages: list[str] = []
        for field, value in detail.items():
            flattened = _flatten_error_detail(value)
            if flattened:
                messages.append(f"{field}: {flattened}")
        return "; ".join(messages)
    if isinstance(detail, list):
        return ", ".join(filter(None, (_flatten_error_detail(item) for item in detail)))
    return str(detail) if detail is not None else ""


def api_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is None:
        return None

    original = response.data
    if isinstance(original, dict) and ("message" in original or "data" in original):
        return response

    message = _flatten_error_detail(original) or "The request could not be completed."
    response.data = {
        "message": message,
        "errors": original,
        "status_code": response.status_code,
    }
    return response
