"""Support for `.codeatlas-ignore` and `.gitignore` files (gitignore-style syntax).

Patterns are matched against repo-relative paths (using forward slashes).
Supports:
- `#` comment lines (full-line only)
- Blank lines ignored
- Glob patterns: `*`, `**`, `?`
- Directory-only patterns ending in `/`
- Negation patterns starting with `!`
- Leading `/` on a pattern (anchor at repo root) is stripped; the pattern
  still matches at any depth.

Patterns from `.gitignore` are loaded first; `.codeatlas-ignore` patterns
(when present) are appended and may negate/override gitignore rules.

Does NOT implement the full gitignore spec (e.g. character classes beyond
basic glob, per-directory `.gitignore` files nested in subfolders).
"""

from __future__ import annotations

import fnmatch
from pathlib import Path


class IgnoreMatcher:
    """Matches repo-relative paths against a set of ignore patterns."""

    def __init__(self, patterns: list[str]) -> None:
        self._positive: list[tuple[str, bool]] = []
        self._negative: list[tuple[str, bool]] = []
        for raw in patterns:
            pattern = raw.strip()
            if not pattern or pattern.startswith("#"):
                continue
            negated = pattern.startswith("!")
            if negated:
                pattern = pattern[1:]
            # Leading "/" anchors the pattern at the repo root in gitignore;
            # we strip it and let the matcher treat the remaining glob as
            # "match at any depth." Close enough for the common cases.
            if pattern.startswith("/"):
                pattern = pattern[1:]
            dir_only = pattern.endswith("/")
            if dir_only:
                pattern = pattern[:-1]
            entry = (pattern, dir_only)
            if negated:
                self._negative.append(entry)
            else:
                self._positive.append(entry)

    def is_ignored(self, rel_path: str, is_dir: bool = False) -> bool:
        """Return True when ``rel_path`` matches an ignore pattern and no
        subsequent negation rescues it."""
        rel = rel_path.replace("\\", "/")
        matched = False
        for pattern, dir_only in self._positive:
            if dir_only and not is_dir:
                continue
            if _matches(rel, pattern):
                matched = True
                break
        if not matched:
            return False
        # Negation: if a later `!pattern` matches, un-ignore
        for pattern, dir_only in self._negative:
            if dir_only and not is_dir:
                continue
            if _matches(rel, pattern):
                return False
        return True


def _matches(rel_path: str, pattern: str) -> bool:
    """Match ``rel_path`` against ``pattern`` using fnmatch semantics.

    Additionally, a pattern without a slash matches any path segment
    (`foo` matches `foo`, `a/foo`, `a/b/foo`).
    """
    if fnmatch.fnmatchcase(rel_path, pattern):
        return True
    # Match any trailing segment if pattern contains no slash
    if "/" not in pattern:
        for segment in rel_path.split("/"):
            if fnmatch.fnmatchcase(segment, pattern):
                return True
    # Match pattern against any suffix of rel_path (e.g. "build" matches "src/build/out.txt")
    parts = rel_path.split("/")
    for i in range(len(parts)):
        sub = "/".join(parts[i:])
        if fnmatch.fnmatchcase(sub, pattern):
            return True
    return False


def _read_pattern_file(path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        return path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return []


def load_ignore_file(repo_root: Path) -> IgnoreMatcher:
    """Load ignore patterns from ``.gitignore`` and ``.codeatlas-ignore``.

    Both files are optional. Patterns from ``.gitignore`` are applied first,
    then ``.codeatlas-ignore`` (so project-specific ignores can add or
    negate the gitignore defaults).
    """
    patterns = _read_pattern_file(repo_root / ".gitignore")
    patterns.extend(_read_pattern_file(repo_root / ".codeatlas-ignore"))
    return IgnoreMatcher(patterns)
