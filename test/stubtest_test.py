import os
import sys
import tempfile

import pytox
from mypy import stubtest

# The extensions: the rest is Python, which is its own stub.
MODULES = [
    "pytox.toxav.toxav",
    "pytox.toxcore.tox",
    "pytox.toxencryptsave.toxencryptsave",
]

ALLOWLIST = """
# Cython's dictionary of module doctests.
pytox\\..*\\.__test__
# Ids are NewTypes, which stubtest doesn't take for types at runtime.
pytox\\.toxcore\\.tox\\.\\w+(Number|Id)
# Cython gives an __init__ without arguments no signature.
pytox\\.toxcore\\.tox\\.Options\\.__init__
"""

if __name__ == "__main__":
    # The stubs sit next to the extensions.
    os.environ["MYPYPATH"] = os.path.dirname(os.path.dirname(pytox.__file__))
    with tempfile.NamedTemporaryFile("w", suffix=".txt") as allowlist:
        allowlist.write(ALLOWLIST)
        allowlist.flush()
        sys.exit(
            stubtest.test_stubs(
                stubtest.parse_options(
                    MODULES + ["--allowlist", allowlist.name])))
