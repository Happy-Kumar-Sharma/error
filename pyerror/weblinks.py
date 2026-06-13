"""
pyerror.weblinks — pre-filled search links for the error you just hit.

Turns an exception into ready-to-click search URLs for Stack Overflow,
Google, and GitHub Issues, so the "copy the message, strip the noise, paste
it into a search box" ritual becomes one click:

    links = pyerror.weblinks.search_links(exc)
    links["stackoverflow"]  # https://stackoverflow.com/search?q=%5Bpython%5D+...

Privacy and quality of the query (this text LEAVES the process, so it gets
the full treatment):
1. The message is scrubbed through pyerror's privacy pipeline first
   (Formatter.scrub_text honoring core._mask_secrets/_secret_keys) — same
   policy as pyerror.ai.
2. Volatile fragments (hex addresses, uuids, long numbers, quoted paths)
   are stripped using pyerror.otel's normalization table, because
   "user 1234567 not found" finds nothing while "user <num> not found"
   finds the canonical Stack Overflow answer.
3. URLs are kept under 400 characters by truncating the message, and the
   query is percent-encoded with urllib.parse.quote_plus.

Both public functions are defensive and never raise.
"""

from __future__ import annotations

from typing import Dict
from urllib.parse import quote_plus

from pyerror.otel import _NORMALIZE_PATTERNS

__all__ = ["search_links", "format_links"]

_MAX_URL_LEN = 400
_INITIAL_MSG_LEN = 200

_BASES = {
    "stackoverflow": ("https://stackoverflow.com/search?q={q}", "Stack Overflow"),
    "google": ("https://www.google.com/search?q={q}", "Google"),
    "github_issues": ("https://github.com/search?q={q}&type=issues", "GitHub Issues"),
}


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


def _normalized_message(exc: BaseException) -> str:
    # Scrub FIRST (nothing secret may survive into the URL), then strip
    # volatile fragments so the search hits canonical results.
    message = _scrub(str(exc))
    for pattern, replacement in _NORMALIZE_PATTERNS:
        message = pattern.sub(replacement, message)
    return " ".join(message.split())


def _build(exc_name: str, message: str, max_msg_len: int) -> Dict[str, str]:
    query = "[python] {}".format(exc_name)
    trimmed = message[:max_msg_len].strip()
    if trimmed:
        query += ": " + trimmed
    encoded = quote_plus(query)
    return {key: template.format(q=encoded)
            for key, (template, _label) in _BASES.items()}


def search_links(exc: BaseException) -> Dict[str, str]:
    """Pre-filled search URLs for `exc`.

    Returns {"stackoverflow": url, "google": url, "github_issues": url}.
    Message is scrubbed + normalized; every URL stays under 400 chars.
    Never raises.
    """
    exc_name = "Exception"
    try:
        exc_name = type(exc).__name__
        message = _normalized_message(exc)
        max_msg_len = _INITIAL_MSG_LEN
        while True:
            links = _build(exc_name, message, max_msg_len)
            if max(len(url) for url in links.values()) < _MAX_URL_LEN:
                return links
            if max_msg_len <= 0:
                return _build(exc_name, "", 0)
            max_msg_len -= 40
    except Exception:
        try:
            return _build(exc_name, "", 0)
        except Exception:
            return {"stackoverflow": "", "google": "", "github_issues": ""}


def format_links(exc: BaseException) -> str:
    """Human-readable, one-link-per-line rendering. Never raises."""
    try:
        links = search_links(exc)
        lines = ["Search this error online:"]
        for key, (_template, label) in _BASES.items():
            url = links.get(key, "")
            if url:
                lines.append("  {:<14} {}".format(label + ":", url))
        return "\n".join(lines)
    except Exception:
        return ""
