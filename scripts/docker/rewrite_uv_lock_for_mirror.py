"""Rewrite uv.lock PyPI URLs for a PEP 503 mirror (e.g. JFrog Artifactory).

Committed lockfiles pin absolute https://files.pythonhosted.org/... artifact URLs and
https://pypi.org/simple registry markers. Setting UV_DEFAULT_INDEX alone does not change
those URLs, so ``uv sync --frozen`` still downloads wheels from PyPI.

When ``UV_DEFAULT_INDEX`` is set to the mirror's simple index (may include userinfo for
auth), this script replaces PyPI hosts with the mirror's host and path prefix. Credentials
are never written into uv.lock — only scheme, host, port, and path are used.

JFrog Artifactory uses /api/pypi/<repo>/simple for the simple API index, but serves
actual wheel files from /<repo>/packages/... (without the /api/pypi/ prefix).
For example:
  - Index: https://host/artifactory/api/pypi/pypi/simple
  - Files: https://host/artifactory/pypi/packages/82/45/.../package.whl

``UV_DEFAULT_INDEX`` must be a simple API URL whose path ends with ``/simple``.
"""

from __future__ import annotations

import os
import sys
from urllib.parse import urlparse

_PYPI_SIMPLE = "https://pypi.org/simple"
_PYHOSTED = "https://files.pythonhosted.org"


def main() -> int:
    index = os.environ.get("UV_DEFAULT_INDEX", "").strip()
    if not index:
        return 0

    parsed = urlparse(index)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        print("rewrite_uv_lock_for_mirror: invalid UV_DEFAULT_INDEX URL", file=sys.stderr)
        return 1

    path = parsed.path.rstrip("/")
    if not path.endswith("/simple"):
        print(
            "rewrite_uv_lock_for_mirror: UV_DEFAULT_INDEX path must end with /simple",
            file=sys.stderr,
        )
        return 1

    base_path = path[: -len("/simple")]
    host = parsed.hostname
    assert host is not None
    if parsed.port is not None and not (
        (parsed.scheme == "https" and parsed.port == 443)
        or (parsed.scheme == "http" and parsed.port == 80)
    ):
        host = f"{host}:{parsed.port}"

    # JFrog Artifactory: Simple API uses /api/pypi/<repo>/simple but actual files
    # are served from the repository path /<repo>/ (no /api/pypi/ prefix)
    # Files.pythonhosted.org URLs already include /packages/, so we only replace the host+path
    # E.g., index: .../api/pypi/pypi/simple → replace host: .../pypi
    if "/api/pypi/" in base_path:
        # Strip /api/pypi/ prefix to get repository path (don't add /packages - already in URL)
        repo_path = base_path.replace("/api/pypi/", "/", 1)
        wheel_prefix = f"{parsed.scheme}://{host}{repo_path}"
    else:
        # Standard PEP 503 mirror
        wheel_prefix = f"{parsed.scheme}://{host}{base_path}"
    
    registry = f"{parsed.scheme}://{host}{path}"

    lock_path = sys.argv[1] if len(sys.argv) > 1 else "uv.lock"
    text = open(lock_path, encoding="utf-8").read()
    text = text.replace(_PYHOSTED, wheel_prefix)
    text = text.replace(_PYPI_SIMPLE, registry)
    open(lock_path, "w", encoding="utf-8").write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
