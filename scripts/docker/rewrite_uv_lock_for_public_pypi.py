"""Rewrite known Artifactory PyPI URLs in uv.lock back to public PyPI."""

from __future__ import annotations

import re
import sys

_PYPI_SIMPLE = "https://pypi.org/simple"
_PYHOSTED_PACKAGES = "https://files.pythonhosted.org/packages/"


def main() -> int:
    lock_path = sys.argv[1] if len(sys.argv) > 1 else "uv.lock"
    with open(lock_path, encoding="utf-8") as lock_file:
        text = lock_file.read()

    text = re.sub(
        r"https://[^\"'\s]+/artifactory/(?:api/pypi/[^/\"'\s]+/)?packages/packages/",
        _PYHOSTED_PACKAGES,
        text,
    )
    text = re.sub(
        r"https://[^\"'\s]+/artifactory/[^/\"'\s]+/packages/",
        _PYHOSTED_PACKAGES,
        text,
    )
    text = re.sub(
        r"https://[^\"'\s]+/artifactory/(?:api/pypi/[^/\"'\s]+|[^/\"'\s]+)/simple",
        _PYPI_SIMPLE,
        text,
    )

    with open(lock_path, "w", encoding="utf-8") as lock_file:
        lock_file.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
