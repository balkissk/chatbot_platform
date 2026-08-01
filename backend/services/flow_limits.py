from urllib.parse import urlparse


MAX_FLOW_NODES = 200
MAX_FLOW_TRANSITIONS = 400
MAX_RUNTIME_STEPS = 100

MIN_CANVAS_POSITION = 0
MAX_CANVAS_POSITION = 50000


def normalize_transition_output_key(label: str | None, condition: str | None) -> str:
    output_key = label if label is not None else condition
    return (output_key or "next").strip().lower()


def is_valid_canvas_position(value) -> bool:
    if isinstance(value, bool) or not isinstance(value, int):
        return False
    return MIN_CANVAS_POSITION <= value <= MAX_CANVAS_POSITION


def is_valid_http_url(value: str | None) -> bool:
    parsed = urlparse((value or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)
