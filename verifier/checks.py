"""Checks shared by the verifiers. Pure functions of their arguments and the files on disk."""

import json
from pathlib import Path


def result(valid, message, *, score=None, **details):
    return {
        "valid": valid,
        "score": float(valid) if score is None else score,
        "message": message,
        "details": details,
    }


def repeated(items):
    return sorted({item for item in items if items.count(item) > 1}, key=str)


def saved_json(workspace, relative):
    """The JSON object at ``relative`` in the workspace, or None when there is no such object."""
    path = Path(workspace) / relative
    if not path.is_file():
        return None
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, RecursionError):  # RecursionError: absurdly nested JSON
        return None
    return value if isinstance(value, dict) else None
