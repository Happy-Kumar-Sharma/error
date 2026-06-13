"""
pyerror.shellhook — shell profile snippets for pyerror integration.

Prints a snippet the user pastes into their shell profile so that running
`pyx script.py` executes the script under pyerror's humanized tracebacks
(`python -m pyerror run`), and `pyerror-last` re-prints the last saved
error report.

Honesty note: shells do not expose a portable hook for "any past command
that exited non-zero", so this integration WRAPS invocations (you opt in
per command via the `pyx` function) rather than retroactively hooking
arbitrary exits. The last-error report only exists for scripts that were
run through `pyx` / `python -m pyerror run`.
"""
import sys

_POWERSHELL_SNIPPET = """# pyerror shell integration (add to your PowerShell $PROFILE)
# Run any script with humanized tracebacks: pyx script.py arg1 arg2
function pyx {
    & python -m pyerror run @args
}
# Re-print the last saved error report
function pyerror-last {
    & python -m pyerror report last
}
"""

_BASH_SNIPPET = """# pyerror shell integration (add to your ~/.bashrc)
# Run any script with humanized tracebacks: pyx script.py arg1 arg2
pyx() {
    python -m pyerror run "$@"
}
# Re-print the last saved error report
alias pyerror-last='python -m pyerror report last'
"""

_ZSH_SNIPPET = """# pyerror shell integration (add to your ~/.zshrc)
# Run any script with humanized tracebacks: pyx script.py arg1 arg2
pyx() {
    python -m pyerror run "$@"
}
# Re-print the last saved error report
alias pyerror-last='python -m pyerror report last'
"""

_SNIPPETS = {
    "powershell": _POWERSHELL_SNIPPET,
    "bash": _BASH_SNIPPET,
    "zsh": _ZSH_SNIPPET,
}


def get_shell_hook(shell: str = "powershell") -> str:
    """Returns the profile snippet for the given shell ('' if unsupported)."""
    return _SNIPPETS.get((shell or "").strip().lower(), "")


def print_shell_hook(shell: str = "powershell") -> str:
    """
    Prints (and returns) the profile snippet for the given shell.
    Supported shells: powershell, bash, zsh.
    """
    snippet = get_shell_hook(shell)
    if not snippet:
        message = "Unsupported shell '{}'. Supported shells: {}".format(
            shell, ", ".join(sorted(_SNIPPETS))
        )
        try:
            sys.stderr.write(message + "\n")
        except Exception:
            pass
        return ""
    try:
        sys.stdout.write(snippet)
        sys.stdout.flush()
    except Exception:
        pass
    return snippet
