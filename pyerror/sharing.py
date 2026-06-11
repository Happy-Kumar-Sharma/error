import base64
import zlib
import json
import os
from typing import Dict, Any
from pyerror.suggestions import SuggestionEngine
from pyerror.formatting import Formatter

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
