"""
SQLAlchemy / psycopg2 / sqlite3 error translator.

`explain_db_error(exc)` returns the SuggestionEngine-style dict for
common database errors; `enrich(exc)` attaches ``__translation__``,
``__why__``, ``__suggestions__`` so the standard pyerror pipeline picks
it up automatically.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

_PATTERNS = [
    {
        "match": re.compile(r"duplicate key value violates unique constraint\s*\"?([^\"\n]+)\"?", re.IGNORECASE),
        "name": "UniqueViolation",
        "translation": "A row with this value already exists; the unique constraint blocks the insert.",
        "why": "Constraint `{0}` requires the offending column(s) to be unique.",
        "suggestions": [
            "Check whether you should be updating the existing row instead of inserting a new one.",
            "Look up the existing row by the duplicated column and decide on an upsert strategy.",
            "If you need parallel safety, use `INSERT ... ON CONFLICT` (Postgres) or `INSERT OR REPLACE` (SQLite).",
        ],
    },
    {
        "match": re.compile(r"violates foreign key constraint\s*\"?([^\"\n]+)\"?", re.IGNORECASE),
        "name": "ForeignKeyViolation",
        "translation": "A foreign-key reference points at a row that doesn't exist (or is being deleted).",
        "why": "Constraint `{0}` requires the referenced parent row to exist.",
        "suggestions": [
            "Insert the parent row first, then the child.",
            "If you're deleting, cascade or NULL the child references before removing the parent.",
            "Verify the reference column actually holds an id from the parent table.",
        ],
    },
    {
        "match": re.compile(r"null value in column\s*\"([^\"]+)\".*not-null constraint", re.IGNORECASE | re.DOTALL),
        "name": "NotNullViolation",
        "translation": "A required column was left empty.",
        "why": "Column `{0}` has a NOT NULL constraint.",
        "suggestions": [
            "Provide a value for `{0}` in your INSERT/UPDATE.",
            "If the column should be optional, drop the NOT NULL constraint in a migration.",
        ],
    },
    {
        "match": re.compile(r"column \"?([^\"\s]+)\"? does not exist", re.IGNORECASE),
        "name": "UndefinedColumn",
        "translation": "The query references a column the table does not have.",
        "why": "Column `{0}` is not defined on the target table.",
        "suggestions": [
            "Check the spelling — typos in column names produce this error.",
            "If the column was added in a migration, verify the migration ran on this database.",
        ],
    },
    {
        "match": re.compile(r"relation \"?([^\"\s]+)\"? does not exist", re.IGNORECASE),
        "name": "UndefinedTable",
        "translation": "The query references a table that does not exist.",
        "why": "Table `{0}` was not found.",
        "suggestions": [
            "Verify the table name and current database/schema.",
            "Run migrations if the table is expected to have been created.",
        ],
    },
    {
        "match": re.compile(r"syntax error at or near \"([^\"]+)\"", re.IGNORECASE),
        "name": "SyntaxError",
        "translation": "Your SQL has a syntax error at the highlighted location.",
        "why": "The parser failed at `{0}`.",
        "suggestions": [
            "Check punctuation and missing keywords around the highlighted token.",
            "If you're building SQL by string concatenation, switch to parameterized queries.",
        ],
    },
    {
        "match": re.compile(r"connection (?:refused|reset|closed)", re.IGNORECASE),
        "name": "ConnectionError",
        "translation": "The database connection could not be established or was lost.",
        "why": "The DB server is unreachable, restarting, or rejecting connections.",
        "suggestions": [
            "Verify host/port, network reachability, and credentials.",
            "Check the DB server logs for crashes or rejected-host messages.",
            "Add connection-pool retries via `@pyerror.retry` for transient failures.",
        ],
    },
    {
        "match": re.compile(r"deadlock detected", re.IGNORECASE),
        "name": "DeadlockDetected",
        "translation": "Two or more transactions are waiting on each other — Postgres aborted yours.",
        "why": "The DB detected a circular lock dependency.",
        "suggestions": [
            "Retry the transaction (deadlocks are often transient).",
            "Acquire locks in a consistent order across all paths to prevent recurrence.",
        ],
    },
    {
        "match": re.compile(r"too many connections", re.IGNORECASE),
        "name": "TooManyConnections",
        "translation": "The database reached its connection limit.",
        "why": "All available DB slots are in use.",
        "suggestions": [
            "Use connection pooling (SQLAlchemy/pgbouncer) and lower max-pool-per-process.",
            "Hunt down connection leaks — make sure sessions/cursors are closed.",
        ],
    },
    {
        "match": re.compile(r"value too long for type", re.IGNORECASE),
        "name": "DataTooLong",
        "translation": "A value is longer than the column allows.",
        "why": "The column's max length is shorter than your value.",
        "suggestions": [
            "Truncate the value or widen the column type in a migration.",
        ],
    },
    {
        "match": re.compile(r"division by zero", re.IGNORECASE),
        "name": "DivisionByZeroSQL",
        "translation": "Your SQL tried to divide by zero.",
        "why": "A computed column or expression produced a zero denominator.",
        "suggestions": [
            "Guard the divisor with NULLIF(divisor, 0) or a CASE expression.",
        ],
    },
]


def _extract_statement(exc: BaseException) -> Optional[str]:
    statement = getattr(exc, "statement", None)
    if statement:
        return str(statement)
    orig = getattr(exc, "orig", None)
    if orig is not None:
        return _extract_statement(orig)
    return None


def explain_db_error(exc: BaseException) -> Dict[str, Any]:
    """Look up `exc` (any DB-error-shaped exception) in the rulebook."""
    msg = str(exc)
    for entry in _PATTERNS:
        m = entry["match"].search(msg)
        if not m:
            continue
        groups = m.groups() or ("",)
        suggestions = [s.format(*groups) for s in entry["suggestions"]]
        why = entry["why"].format(*groups)
        try:
            from pyerror.formatting import Formatter
            statement = _extract_statement(exc)
            if statement:
                statement = Formatter.scrub_text(statement)
        except Exception:
            statement = _extract_statement(exc)
        return {
            "name": entry["name"],
            "translation": entry["translation"],
            "why": why,
            "suggestions": suggestions,
            "statement": statement,
        }
    return {
        "name": "DatabaseError",
        "translation": "The database returned an error.",
        "why": str(exc),
        "suggestions": ["Check the DB driver/server logs for the underlying SQLSTATE code."],
        "statement": _extract_statement(exc),
    }


def enrich(exc: BaseException) -> BaseException:
    """Stamp pyerror diagnostic attributes onto a DB exception."""
    details = explain_db_error(exc)
    try:
        exc.__translation__ = details["translation"]
        exc.__why__ = details["why"]
        exc.__suggestions__ = details["suggestions"]
        if details.get("statement"):
            exc.__sql_statement__ = details["statement"]
    except Exception:
        pass
    return exc


def install_sqlalchemy_hook(engine: Any = None) -> bool:
    """Install a SQLAlchemy `handle_error` listener that calls :func:`enrich`."""
    try:
        from sqlalchemy import event  # type: ignore
        from sqlalchemy.engine import Engine  # type: ignore
    except ImportError:
        raise ImportError("install_sqlalchemy_hook requires `pip install sqlalchemy`.")
    target = engine or Engine

    @event.listens_for(target, "handle_error")
    def _on_error(context):
        try:
            enrich(context.original_exception)
        except Exception:
            pass

    return True
