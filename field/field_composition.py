"""Deprecated compatibility shim for the π field compositor.

The kernel uses :mod:`pi_fields` directly. This module remains only so older
imports of ``field_composition`` do not fail outright. New code should use
``pi_fields.PiFieldCompositor``, ``calc_wind``, and ``calc_attraction_well``.
"""

from __future__ import annotations

import warnings

from pi_fields import PiFieldCompositor, calc_wind, calc_attraction_well, default_field_compositor

warnings.warn(
    "field_composition is deprecated; import pi_fields instead",
    DeprecationWarning,
    stacklevel=2,
)

# Old name kept as an alias.
πFieldCompositor = PiFieldCompositor

__all__ = [
    "πFieldCompositor",
    "PiFieldCompositor",
    "calc_wind",
    "calc_attraction_well",
    "default_field_compositor",
]
