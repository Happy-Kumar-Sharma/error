"""
pyerror.rootcause — confidence-ranked root cause for chained exceptions.

A production traceback is usually three exceptions deep:

    ConnectionRefusedError          <- the actual problem
    ... during handling ...
    psycopg2.OperationalError       <- the library's wrapper
    ... raised from ...
    AppStartupError                 <- your wrapper

This module walks the __cause__/__context__ chain (cycle-safe, same walk as
pyerror.otel._chain_depth) and ranks the links to answer "which one do I
actually fix?":

    report = pyerror.rootcause.analyze_chain(exc)
    report.verdict.exc_type    # "ConnectionRefusedError"
    report.confidence          # "high" / "medium" / "low"
    report.show()

Heuristics (in decreasing weight):
1. An explicit `raise X from Y` is a deliberate statement that Y is the
   cause — it outweighs the implicit "during handling of" __context__.
2. The deepest exception in the chain is the default origin.
3. Links whose deepest frame is user code (not site-packages / stdlib) are
   preferred: you can only fix your own code.
Confidence is "high" when the winning link is BOTH an explicit cause and
user code, "medium" when one of the two holds, "low" otherwise.

analyze_chain never raises into the host application.
"""

from __future__ import annotations

import os
import sys
import sysconfig
import traceback
from dataclasses import dataclass, field
from typing import List, Optional

__all__ = ["analyze_chain", "RootCauseReport", "ChainLink"]

_EXPLICIT_WEIGHT = 5
_USER_CODE_WEIGHT = 3


@dataclass
class ChainLink:
    """One exception in a __cause__/__context__ chain."""

    exc_type: str
    message: str
    explicit: bool      # True: designated via `raise ... from ...` (__cause__)
    depth: int          # 0 = outermost (the exception you caught)
    location: str       # "file.py:lineno in func" of the deepest user frame
    is_user_code: bool  # deepest frame is outside site-packages / stdlib


@dataclass
class RootCauseReport:
    links: List[ChainLink] = field(default_factory=list)
    verdict: Optional[ChainLink] = None
    confidence: str = "low"
    reasoning: str = ""

    def __str__(self) -> str:
        lines = ["Exception chain ({} link{}):".format(
            len(self.links), "" if len(self.links) == 1 else "s")]
        for index, link in enumerate(self.links):
            marker = "*" if link is self.verdict else " "
            origin = "user code" if link.is_user_code else "library/stdlib"
            lines.append("{} [{}] {}: {}".format(
                marker, link.depth, link.exc_type, link.message[:120]))
            lines.append("       at {} ({})".format(link.location or "?", origin))
            if index + 1 < len(self.links):
                nxt = self.links[index + 1]
                lines.append("       {} by:".format(
                    "explicitly caused (raise ... from)" if nxt.explicit
                    else "implicitly preceded (during handling)"))
        if self.verdict is not None:
            lines.append("Root cause ({} confidence): {}: {}".format(
                self.confidence, self.verdict.exc_type, self.verdict.message[:120]))
        if self.reasoning:
            lines.append("Reasoning: " + self.reasoning)
        return "\n".join(lines)

    def show(self) -> None:
        print(self.__str__())


# ---------------------------------------------------------------------------
# Frame classification
# ---------------------------------------------------------------------------

def _is_user_code(filename: str) -> bool:
    if not filename or filename.startswith("<"):
        return False
    lowered = filename.lower().replace("\\", "/")
    if "site-packages" in lowered or "dist-packages" in lowered:
        return False
    try:
        stdlib = sysconfig.get_paths()["stdlib"].lower().replace("\\", "/")
        if stdlib and lowered.startswith(stdlib):
            return False
    except Exception:
        pass
    try:
        if lowered.startswith(sys.base_prefix.lower().replace("\\", "/") + "/lib"):
            return False
    except Exception:
        pass
    return True


def _make_link(exc: BaseException, depth: int, explicit: bool) -> ChainLink:
    location = ""
    is_user = False
    try:
        tb = getattr(exc, "__traceback__", None)
        if tb is not None:
            frames = traceback.extract_tb(tb)
            if frames:
                user_frames = [f for f in frames if _is_user_code(f.filename)]
                frame = (user_frames or frames)[-1]
                is_user = bool(user_frames)
                location = "{}:{} in {}".format(
                    os.path.basename(frame.filename), frame.lineno, frame.name)
    except Exception:
        pass
    return ChainLink(
        exc_type=type(exc).__qualname__,
        message=str(exc),
        explicit=explicit,
        depth=depth,
        location=location,
        is_user_code=is_user,
    )


def _walk_chain(exc: BaseException) -> List[ChainLink]:
    """Cycle-safe __cause__/__context__ walk (cf. otel._chain_depth)."""
    links: List[ChainLink] = []
    seen = {id(exc)}
    current: Optional[BaseException] = exc
    depth = 0
    explicit = False  # the outermost link was not "caused" by anything above it
    while current is not None:
        links.append(_make_link(current, depth, explicit))
        cause = getattr(current, "__cause__", None)
        if cause is not None:
            nxt, explicit = cause, True
        elif not getattr(current, "__suppress_context__", False):
            nxt, explicit = getattr(current, "__context__", None), False
        else:
            nxt = None
        if nxt is None or id(nxt) in seen:
            break
        seen.add(id(nxt))
        current = nxt
        depth += 1
    return links


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def _score(link: ChainLink) -> int:
    score = link.depth  # deeper = closer to the origin
    if link.explicit:
        score += _EXPLICIT_WEIGHT
    if link.is_user_code:
        score += _USER_CODE_WEIGHT
    return score


def analyze_chain(exc: BaseException) -> RootCauseReport:
    """Rank the exception chain of `exc` and pick the likely root cause.

    Never raises; on internal failure returns a single-link, low-confidence
    report for `exc` itself.
    """
    try:
        links = _walk_chain(exc)
        if not links:
            links = [_make_link(exc, 0, False)]

        # max() keeps the FIRST best on ties; iterate deepest-first so a tie
        # resolves to the deeper link (default-origin heuristic).
        verdict = max(reversed(links), key=_score)

        if verdict.explicit and verdict.is_user_code:
            confidence = "high"
        elif verdict.explicit or verdict.is_user_code:
            confidence = "medium"
        else:
            confidence = "low"

        reasons: List[str] = []
        if len(links) == 1:
            reasons.append("the exception is not chained")
        else:
            if verdict.depth == links[-1].depth:
                reasons.append(
                    "it is the deepest exception in a {}-link chain".format(len(links)))
            else:
                reasons.append(
                    "it outranks deeper links (depth {} of {})".format(
                        verdict.depth, links[-1].depth))
            if verdict.explicit:
                reasons.append("it was explicitly designated via `raise ... from ...`")
            else:
                reasons.append("it entered the chain implicitly (during handling)")
        if verdict.is_user_code:
            reasons.append("it originates in user code ({})".format(
                verdict.location or "unknown location"))
        elif verdict.location:
            reasons.append("it originates in library/stdlib code ({})".format(
                verdict.location))

        reasoning = "{} is the likely root cause because {}.".format(
            verdict.exc_type, "; ".join(reasons))
        return RootCauseReport(
            links=links, verdict=verdict,
            confidence=confidence, reasoning=reasoning,
        )
    except Exception:
        fallback = ChainLink(
            exc_type=type(exc).__qualname__ if isinstance(exc, BaseException) else "Exception",
            message=str(exc), explicit=False, depth=0,
            location="", is_user_code=False,
        )
        return RootCauseReport(
            links=[fallback], verdict=fallback, confidence="low",
            reasoning="Chain analysis failed internally; reporting the caught "
                      "exception itself.",
        )
