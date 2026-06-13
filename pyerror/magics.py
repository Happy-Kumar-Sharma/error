"""IPython magics for pyerror.

Load with::

    %load_ext pyerror.magics

Then::

    %pyerror on         # enable humanize()
    %pyerror beginner   # beginner_mode
    %pyerror off        # restore
    %explain            # show humanized diagnostics for the last exception
"""
from __future__ import annotations


def _pyerror_line_magic(line):
    arg = (line or "").strip().lower() or "on"
    import pyerror
    if arg == "on":
        pyerror.humanize(True)
        return "pyerror: humanize ON"
    if arg == "off":
        pyerror.humanize(False)
        return "pyerror: humanize OFF"
    if arg == "beginner":
        pyerror.beginner_mode(True)
        return "pyerror: beginner mode ON"
    return "pyerror magic: use 'on', 'off', or 'beginner'"


def _explain_line_magic(line):
    import pyerror
    pyerror.inspect_last_error()


def register_magics(ipython=None):
    """Register magics on the given IPython instance (or the active one)."""
    if ipython is None:
        try:
            from IPython import get_ipython
            ipython = get_ipython()
        except Exception:
            ipython = None
    if ipython is None:
        return False
    try:
        ipython.register_magic_function(_pyerror_line_magic, "line", "pyerror")
        ipython.register_magic_function(_explain_line_magic, "line", "explain")
        return True
    except Exception:
        return False


def load_ipython_extension(ipython):
    """IPython extension entry point — invoked by `%load_ext pyerror.magics`."""
    register_magics(ipython)
