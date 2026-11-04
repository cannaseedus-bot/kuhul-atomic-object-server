"""Repository-root entry point for the Micronaut task advisor."""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from micronaut.advisor import main

if __name__ == "__main__":
    raise SystemExit(main())
