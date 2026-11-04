"""Convenience entry point for the key-grammar kit SyntaxCompiler."""
from __future__ import annotations

import sys
from pathlib import Path

_IMPL = Path(__file__).resolve().parents[2] / "vendor" / "key-grammar-kit" / "tools" / "grammar"
sys.path.insert(0, str(_IMPL))
from syntax_compiler import *  # noqa: F401,F403,E402
from syntax_compiler import main

if __name__ == "__main__":
    raise SystemExit(main())
