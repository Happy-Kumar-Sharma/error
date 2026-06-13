"""
Pretty errors for CLI applications (argparse, click, typer).
"""
from __future__ import annotations

import functools
import sys
from typing import Any, Callable, Optional


def humanize_cli(func: Optional[Callable] = None, *, mode: str = "compact"):
    """Decorator: catch unexpected exceptions, print humanized output, exit 1.

    SystemExit, KeyboardInterrupt, and click.ClickException are passed
    through unchanged so CLI flow control still works.
    """
    def _decorate(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return fn(*args, **kwargs)
            except (SystemExit, KeyboardInterrupt):
                raise
            except BaseException as exc:
                try:
                    from click.exceptions import ClickException  # type: ignore
                    if isinstance(exc, ClickException):
                        raise
                except ImportError:
                    pass
                try:
                    from pyerror.formatting import Formatter
                    from pyerror import core as _core
                    sys.stderr.write(Formatter.format_cli(
                        exc, mode=mode,
                        mask_secrets=_core._mask_secrets,
                        secret_keys=_core._secret_keys,
                    ))
                except Exception:
                    import traceback
                    traceback.print_exception(type(exc), exc, exc.__traceback__)
                raise SystemExit(1)
        return wrapper

    if func is not None and callable(func):
        return _decorate(func)
    return _decorate


def install_argparse_handler(parser) -> None:
    """Wrap argparse's error() and parse_args() with friendlier messages."""
    _orig_error = parser.error
    _orig_parse = parser.parse_args

    def _friendly_error(message):
        sys.stderr.write("\npyerror: I couldn't understand the arguments — {}\n".format(message))
        sys.stderr.write(parser.format_usage())
        raise SystemExit(2)

    def _friendly_parse(args=None, namespace=None):
        try:
            return _orig_parse(args=args, namespace=namespace)
        except SystemExit:
            raise
        except BaseException as exc:
            try:
                from pyerror.formatting import Formatter
                from pyerror import core as _core
                sys.stderr.write(Formatter.format_cli(
                    exc, mode="compact",
                    mask_secrets=_core._mask_secrets,
                    secret_keys=_core._secret_keys,
                ))
            except Exception:
                pass
            raise

    parser.error = _friendly_error
    parser.parse_args = _friendly_parse


def click_excepthook() -> Callable:
    """Return a callable that can wrap a click command's return path."""
    def _hook(exc: BaseException) -> int:
        try:
            from pyerror.formatting import Formatter
            from pyerror import core as _core
            sys.stderr.write(Formatter.format_cli(
                exc, mode="compact",
                mask_secrets=_core._mask_secrets,
                secret_keys=_core._secret_keys,
            ))
        except Exception:
            import traceback
            traceback.print_exception(type(exc), exc, exc.__traceback__)
        return 1
    return _hook
