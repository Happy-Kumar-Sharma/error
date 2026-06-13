"""
Quiz mode — show the error, ask the learner to pick the cause, then reveal.
"""
from __future__ import annotations

import random
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


_DISTRACTORS = [
    "You forgot to call .copy() on the dictionary before mutating it.",
    "Python ran out of memory during this operation.",
    "A network call to localhost timed out inside the standard library.",
    "The variable was shadowed by a function argument with the same name.",
    "An import-time side effect modified a global before this line ran.",
    "Garbage collection deallocated the object mid-call.",
]


@dataclass
class QuizResult:
    correct: Optional[bool]
    chosen: str
    answer: str
    options: List[str] = field(default_factory=list)


_HISTORY: List[QuizResult] = []


def quiz_history() -> Dict[str, Any]:
    correct = sum(1 for r in _HISTORY if r.correct)
    return {"total": len(_HISTORY), "correct": correct, "results": list(_HISTORY)}


def reset_history() -> None:
    _HISTORY.clear()


def quiz(exc: Optional[BaseException] = None,
         input_fn: Callable[[str], str] = input,
         output=None,
         rng: Optional[random.Random] = None) -> QuizResult:
    out = output or sys.stdout
    if exc is None:
        _, exc, _ = sys.exc_info()
    if exc is None:
        out.write("pyerror quiz: no active exception.\n")
        return QuizResult(correct=None, chosen="", answer="", options=[])

    rng = rng or random.Random()

    try:
        from pyerror.suggestions import SuggestionEngine
        details = SuggestionEngine.get_details(exc)
    except Exception:
        details = {"name": type(exc).__name__, "message": str(exc), "translation": ""}

    answer = details.get("translation") or "Unknown root cause"
    distractors = rng.sample(_DISTRACTORS, k=min(3, len(_DISTRACTORS)))
    options = list(distractors) + [answer]
    rng.shuffle(options)
    answer_index = options.index(answer)

    out.write("\n=== pyerror quiz ===\n")
    out.write("Error: {}: {}\n".format(details.get("name", ""), details.get("message", "")))
    out.write("Which of these best explains why this happened?\n")
    for i, opt in enumerate(options):
        out.write("  {}) {}\n".format(chr(ord('A') + i), opt))

    try:
        choice = (input_fn("Your answer (A-D): ") or "").strip().upper()
    except (EOFError, KeyboardInterrupt):
        result = QuizResult(correct=None, chosen="", answer=answer, options=options)
        _HISTORY.append(result)
        return result

    chosen_index = ord(choice) - ord('A') if choice and choice[0].isalpha() else -1
    correct = (chosen_index == answer_index)
    chosen = options[chosen_index] if 0 <= chosen_index < len(options) else ""

    if correct:
        out.write("\n✅ Nice — that's right!\n")
    else:
        out.write("\n❌ Not quite. The right answer was {}.\n".format(chr(ord('A') + answer_index)))
    out.write("\nFull explanation:\n  {}\n".format(answer))
    if details.get("why"):
        out.write("  Why: {}\n".format(details["why"]))
    for s in (details.get("suggestions") or [])[:3]:
        out.write("  - {}\n".format(s))

    result = QuizResult(correct=correct, chosen=chosen, answer=answer, options=options)
    _HISTORY.append(result)
    return result
