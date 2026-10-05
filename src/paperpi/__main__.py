"""``python -m paperpi``: the same as the ``paperpi`` command."""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
