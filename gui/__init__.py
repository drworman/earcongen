"""Graphical front end for earcongen.

Kept as a package beside the scripts rather than inside them: earcongen.py
and earconcheck.py remain single-file, dependency-light tools that run
with numpy alone, and nothing here is imported unless the GUI is started.
"""

from __future__ import annotations

__all__ = ["app", "params", "paths", "player", "widgets", "worker"]
