"""sedlite: a pure-Python implementation of the sed stream editor."""
from .editor import run

__version__ = "0.2.0"
__all__ = ["run", "main"]


def main(argv=None):
    """Command-line entry point; returns the exit status."""
    import sys

    if argv is None:
        argv = sys.argv[1:]
    status = run(argv, sys.stdin.buffer, sys.stdout.buffer, sys.stderr)
    sys.stdout.flush()
    return status
