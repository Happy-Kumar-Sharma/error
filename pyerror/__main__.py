"""Enables `python -m pyerror <subcommand>`."""
import sys
from pyerror.cli import main

if __name__ == "__main__":
    sys.exit(main())
