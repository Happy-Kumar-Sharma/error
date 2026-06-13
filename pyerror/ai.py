"""
pyerror.ai — optional LLM-powered error explanation and fix suggestion.

Design principles:
1. ZERO new dependencies — uses stdlib urllib, so the core package stays light.
2. PRIVACY FIRST — everything sent to the model passes through pyerror's own
   scrubbing pipeline first; locals are included only with include_locals=True;
   `provider="ollama"` keeps everything on the user's machine.
3. EXPLICIT OPT-IN — nothing is ever sent anywhere unless the user calls
   ai_explain() themselves and supplies a key (or runs a local model).

Usage:
    import pyerror
    try:
        risky()
    except Exception as exc:
        result = pyerror.ai_explain(exc)            # ANTHROPIC_API_KEY env
        result = pyerror.ai_explain(exc, provider="openai")
        result = pyerror.ai_explain(exc, provider="ollama", model="llama3.2")
        result.show()
        print(result.fix_code)

Suggested extra:  pip install pyerror-intel[ai]   (no deps needed — the extra
is just a documented marker, or pin `httpx` later if you outgrow urllib).
"""

from __future__ import annotations

import json
import os
import textwrap
import traceback
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

__all__ = ["ai_explain", "AIExplanation", "AIProviderError"]

DEFAULT_MODELS = {
    "anthropic": "claude-haiku-4-5",
    "openai": "gpt-4o-mini",
    "ollama": "llama3.2",
}

_SYSTEM_PROMPT = (
    "You are an expert Python debugging assistant inside the pyerror library. "
    "Given an exception report, respond ONLY with a JSON object (no markdown "
    "fences, no prose outside the JSON) with exactly these keys: "
    '"explanation" (2-3 plain-English sentences a junior dev understands), '
    '"root_cause" (one sentence), '
    '"fix_code" (a minimal corrected code snippet, or empty string), '
    '"suggestions" (array of 2-4 short actionable steps), '
    '"confidence" ("high", "medium", or "low").'
)


class AIProviderError(RuntimeError):
    """Raised when the AI provider call fails (network, auth, bad response)."""


@dataclass
class AIExplanation:
    explanation: str
    root_cause: str
    fix_code: str
    suggestions: List[str]
    confidence: str
    provider: str
    model: str
    raw: Dict[str, Any] = field(default_factory=dict, repr=False)

    def show(self) -> None:
        """Render to terminal. Swap in your rich panel renderer here."""
        print("\n[AI explanation — {} / {} — confidence: {}]".format(
            self.provider, self.model, self.confidence))
        print("  Why : " + self.explanation)
        print("  Root: " + self.root_cause)
        if self.suggestions:
            print("  Fix steps:")
            for index, step in enumerate(self.suggestions, 1):
                print("    {}. {}".format(index, step))
        if self.fix_code:
            print("  Suggested code:\n" + textwrap.indent(self.fix_code, "    "))


# ---------------------------------------------------------------------------
# Context building (privacy-aware)
# ---------------------------------------------------------------------------

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


def _build_context(
    exc: BaseException,
    include_locals: bool,
    max_chars: int = 6000,
) -> str:
    parts: List[str] = []
    parts.append("Exception type: " + type(exc).__qualname__)
    parts.append("Message: " + _scrub(str(exc)))

    tb = getattr(exc, "__traceback__", None)
    if tb is not None:
        tb_text = "".join(traceback.format_exception(type(exc), exc, tb))
        parts.append("Traceback:\n" + _scrub(tb_text))

    if include_locals:
        captured = getattr(exc, "__captured_locals__", None)
        if captured:
            # captured locals are already masked by @capture_locals
            parts.append("Captured locals (secrets masked): "
                         + json.dumps(captured, default=str))

    context = "\n\n".join(parts)
    return context[:max_chars]


# ---------------------------------------------------------------------------
# Provider backends (stdlib HTTP)
# ---------------------------------------------------------------------------

def _http_json(url: str, payload: Dict[str, Any], headers: Dict[str, str],
               timeout: float) -> Dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        body = err.read().decode("utf-8", errors="replace")[:500]
        raise AIProviderError(
            "Provider returned HTTP {}: {}".format(err.code, body)) from err
    except urllib.error.URLError as err:
        raise AIProviderError("Network error: {}".format(err.reason)) from err


def _call_anthropic(context: str, model: str, api_key: str,
                    timeout: float) -> str:
    data = _http_json(
        "https://api.anthropic.com/v1/messages",
        {
            "model": model,
            "max_tokens": 1024,
            "system": _SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": context}],
        },
        {"x-api-key": api_key, "anthropic-version": "2023-06-01"},
        timeout,
    )
    blocks = data.get("content", [])
    return "".join(b.get("text", "") for b in blocks if b.get("type") == "text")


def _call_openai(context: str, model: str, api_key: str,
                 timeout: float) -> str:
    data = _http_json(
        "https://api.openai.com/v1/chat/completions",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            "response_format": {"type": "json_object"},
        },
        {"Authorization": "Bearer " + api_key},
        timeout,
    )
    return data["choices"][0]["message"]["content"]


def _call_ollama(context: str, model: str, base_url: str,
                 timeout: float) -> str:
    data = _http_json(
        base_url.rstrip("/") + "/api/chat",
        {
            "model": model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": context},
            ],
            "stream": False,
            "format": "json",
        },
        {},
        timeout,
    )
    return data["message"]["content"]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def ai_explain(
    exc: BaseException,
    provider: str = "anthropic",
    model: Optional[str] = None,
    api_key: Optional[str] = None,
    include_locals: bool = False,
    timeout: float = 30.0,
    ollama_url: str = "http://localhost:11434",
) -> AIExplanation:
    """Explain an exception with an LLM. Explicit opt-in, privacy-scrubbed.

    api_key falls back to ANTHROPIC_API_KEY / OPENAI_API_KEY env vars.
    Raises AIProviderError on failure — callers can fall back to the
    built-in rule-based pyerror.explain().
    """
    provider = provider.lower()
    if provider not in DEFAULT_MODELS:
        raise AIProviderError(
            "Unknown provider '{}'. Use one of: {}".format(
                provider, ", ".join(sorted(DEFAULT_MODELS))))
    model = model or DEFAULT_MODELS[provider]
    context = _build_context(exc, include_locals=include_locals)

    if provider == "anthropic":
        key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        if not key:
            raise AIProviderError("Set ANTHROPIC_API_KEY or pass api_key=.")
        raw_text = _call_anthropic(context, model, key, timeout)
    elif provider == "openai":
        key = api_key or os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise AIProviderError("Set OPENAI_API_KEY or pass api_key=.")
        raw_text = _call_openai(context, model, key, timeout)
    else:  # ollama — fully local, nothing leaves the machine
        raw_text = _call_ollama(context, model, ollama_url, timeout)

    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    try:
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        # Model ignored the schema — still return something useful.
        parsed = {"explanation": cleaned[:1000], "root_cause": "",
                  "fix_code": "", "suggestions": [], "confidence": "low"}

    return AIExplanation(
        explanation=str(parsed.get("explanation", "")),
        root_cause=str(parsed.get("root_cause", "")),
        fix_code=str(parsed.get("fix_code", "")),
        suggestions=[str(s) for s in parsed.get("suggestions", [])][:4],
        confidence=str(parsed.get("confidence", "medium")),
        provider=provider,
        model=model,
        raw=parsed,
    )
