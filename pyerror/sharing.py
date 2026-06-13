import base64
import json
import os
import sys
import time
import urllib.request
import urllib.error
import zlib
from typing import Any, Dict, List, Optional
from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter

_community_endpoint: Optional[str] = None
_community_enabled: bool = False
_community_token: Optional[str] = None


def configure_community(endpoint: Optional[str] = None,
                        enabled: Optional[bool] = None,
                        token: Optional[str] = None) -> None:
    """Configure the opt-in anonymous community fix-sharing endpoint.

    NO default endpoint is shipped — supply your own server URL. The
    payload contract is documented in :func:`share_fix`.
    """
    global _community_endpoint, _community_enabled, _community_token
    if endpoint is not None:
        _community_endpoint = endpoint.rstrip("/")
    if enabled is not None:
        _community_enabled = bool(enabled)
    if token is not None:
        _community_token = token


def share_fix(exc: BaseException, note: str, timeout: float = 3.0) -> bool:
    """Anonymously upload a fingerprint+note pair.

    The payload is intentionally minimal: ``fingerprint`` (16-char hash),
    ``exc_type``, scrubbed ``note``, ``pyerror_version``, and ``ts``.
    The exception message, file paths, locals, and traceback are NEVER
    transmitted.
    """
    if not _community_enabled or not _community_endpoint:
        sys.stderr.write("pyerror.share_fix: community sharing is not enabled.\n")
        return False
    try:
        from pyerror.otel import fingerprint
        fp = fingerprint(exc)
    except Exception:
        fp = ""
    try:
        import pyerror as _pkg
        version = getattr(_pkg, "__version__", "")
    except Exception:
        version = ""
    payload = {
        "fingerprint": fp,
        "exc_type": type(exc).__name__,
        "note": Formatter.scrub_text(str(note or "")),
        "pyerror_version": version,
        "ts": time.time(),
    }
    headers = {"Content-Type": "application/json"}
    if _community_token:
        headers["Authorization"] = "Bearer " + _community_token
    req = urllib.request.Request(
        _community_endpoint + "/fixes",
        data=json.dumps(payload).encode("utf-8"),
        method="POST", headers=headers,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return 200 <= resp.status < 300
    except Exception as exc_:
        sys.stderr.write("pyerror.share_fix: POST failed ({}).\n".format(exc_))
        return False


def fetch_fixes(exc: BaseException, timeout: float = 3.0) -> List[Dict[str, Any]]:
    """Look up community-shared notes for this exception's fingerprint."""
    if not _community_enabled or not _community_endpoint:
        return []
    try:
        from pyerror.otel import fingerprint
        fp = fingerprint(exc)
    except Exception:
        return []
    if not fp:
        return []
    url = _community_endpoint + "/fixes/" + fp
    try:
        req = urllib.request.Request(url)
        if _community_token:
            req.add_header("Authorization", "Bearer " + _community_token)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8")) or []
    except Exception:
        return []

def generate_share_link(exc: BaseException) -> str:
    """
    Serializes, compresses, and base64-encodes the exception information
    to produce a self-contained error sharing link.
    """
    details = SuggestionEngine.get_details(exc)
    frames = Formatter.extract_frames(exc)
    
    # Minimize frames to save URL space
    minified_frames = []
    for f in frames:
        minified_frames.append({
            "file": os.path.basename(f["filename"]) if "filename" in f else "unknown",
            "line": f.get("lineno", 0),
            "func": f.get("func_name", "unknown"),
            "code": f.get("code_line", "")
        })

    payload = {
        "type": details["name"],
        "message": details["message"],
        "translation": details["translation"],
        "why": details["why"],
        "suggestions": details["suggestions"],
        "traceback": minified_frames
    }

    # Add recent logs if available
    from pyerror.logging_handler import get_recent_logs
    recent_logs = get_recent_logs()
    if recent_logs:
        payload["recent_logs"] = recent_logs

    try:
        # Encode JSON to bytes, compress using zlib, base64 encode
        json_bytes = json.dumps(payload).encode("utf-8")
        compressed = zlib.compress(json_bytes)
        b64_encoded = base64.urlsafe_b64encode(compressed).decode("utf-8")
        
        # Static viewer page URL hosted on GitHub Pages
        base_url = "https://happy-kumar-sharma.github.io/error/viewer.html"
        return f"{base_url}?data={b64_encoded}"
    except Exception as e:
        return f"Error generating share link: {e}"
