"""Repository-root entry point for the bounded Micronaut task worker."""
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from micronaut.worker import main

if __name__ == "__main__":
    raise SystemExit(main())
