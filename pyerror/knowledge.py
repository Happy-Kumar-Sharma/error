"""
pyerror.knowledge — a local, per-developer error knowledge base.

The third time you hit "psycopg2.OperationalError: SSL SYSCALL error", you
have already forgotten what fixed it the first two times. This module lets
you attach notes to an error and get them back the next time the *same*
error occurs — across runs, across projects:

    try:
        connect()
    except Exception as exc:
        pyerror.knowledge.learn(exc, "VPN was down — restart wireguard")
        ...
    # next week:
    for entry in pyerror.knowledge.recall(exc):
        print(entry["note"], entry["created"])

Storage and matching:
- Errors are keyed by pyerror.otel.fingerprint(exc), so recurrences with
  different ids/paths/addresses in the message still match.
- Notes live in a single JSON file: explicit kb_path argument, else the
  PYERROR_KB environment variable, else ~/.pyerror_kb.json.
- Notes are scrubbed through pyerror's privacy pipeline BEFORE they are
  written to disk (same policy as pyerror.ai): a note like
  "retry with password=hunter2" never stores the secret.
- Multiple notes per fingerprint accumulate, each with an ISO timestamp.
- All public functions are defensive: recall() returns [] and never raises;
  learn()/forget() swallow I/O failures rather than crash the host app.
"""

from __future__ import annotations

import json
import os
from datetime import datetime
from typing import Any, Dict, List, Optional

from pyerror.otel import fingerprint

__all__ = ["learn", "recall", "forget"]

_ENV_VAR = "PYERROR_KB"
_DEFAULT_BASENAME = ".pyerror_kb.json"


def _scrub(text: str) -> str:
    """Run text through pyerror's scrubbing pipeline when available."""
    try:
        from pyerror import core
        from pyerror.formatting import Formatter

        if not core._mask_secrets:
            return text
        return Formatter.scrub_text(text, core._secret_keys)
    except Exception:
        return text


def _kb_file(kb_path: Optional[str]) -> str:
    if kb_path:
        return kb_path
    env_path = os.environ.get(_ENV_VAR, "")
    if env_path:
        return env_path
    return os.path.join(os.path.expanduser("~"), _DEFAULT_BASENAME)


def _load(path: str) -> Dict[str, List[Dict[str, Any]]]:
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def _save(path: str, data: Dict[str, List[Dict[str, Any]]]) -> bool:
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        return True
    except Exception:
        return False


def learn(exc: BaseException, note: str, kb_path: Optional[str] = None) -> Optional[str]:
    """Store a (scrubbed) note for this error's fingerprint.

    Returns the fingerprint the note was filed under, or None on failure.
    Never raises.
    """
    try:
        fp = fingerprint(exc)
        path = _kb_file(kb_path)
        data = _load(path)
        entries = data.setdefault(fp, [])
        if not isinstance(entries, list):  # repair a corrupted slot
            entries = []
            data[fp] = entries
        entries.append({
            "note": _scrub(str(note)),
            "created": datetime.utcnow().isoformat() + "Z",
        })
        if not _save(path, data):
            return None
        return fp
    except Exception:
        return None


def recall(exc: BaseException, kb_path: Optional[str] = None) -> List[Dict[str, Any]]:
    """Return every note previously learned for this error.

    Each entry is {"note": str, "created": str, "fingerprint": str}.
    Returns [] when nothing is known (or on any failure). Never raises.
    """
    try:
        fp = fingerprint(exc)
        entries = _load(_kb_file(kb_path)).get(fp, [])
        if not isinstance(entries, list):
            return []
        results: List[Dict[str, Any]] = []
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            results.append({
                "note": str(entry.get("note", "")),
                "created": str(entry.get("created", "")),
                "fingerprint": fp,
            })
        return results
    except Exception:
        return []


def forget(fingerprint_value: str, kb_path: Optional[str] = None) -> bool:
    """Delete all notes stored under a fingerprint. Never raises."""
    try:
        path = _kb_file(kb_path)
        data = _load(path)
        if fingerprint_value not in data:
            return False
        del data[fingerprint_value]
        return _save(path, data)
    except Exception:
        return False
