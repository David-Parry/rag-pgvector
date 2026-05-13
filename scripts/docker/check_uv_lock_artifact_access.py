"""Return success when a rewritten uv.lock artifact URL is reachable.

This is a Docker build preflight for private PyPI mirrors. It checks one artifact
URL from the lockfile using credentials from ``~/.netrc`` when available.
"""

from __future__ import annotations

import base64
import netrc
import os
import sys
import tomllib
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlparse


def _artifact_urls(lock_path: Path) -> list[str]:
    lock = tomllib.loads(lock_path.read_text(encoding="utf-8"))
    urls: list[str] = []
    for package in lock.get("package", []):
        sdist = package.get("sdist")
        if isinstance(sdist, dict) and isinstance(sdist.get("url"), str):
            urls.append(sdist["url"])
        for wheel in package.get("wheels", []):
            if isinstance(wheel, dict) and isinstance(wheel.get("url"), str):
                urls.append(wheel["url"])
    return urls


def _basic_auth_for(host: str) -> str | None:
    netrc_path = Path(os.environ.get("UV_NETRC_FILE", "/root/.netrc"))
    if not netrc_path.is_file():
        return None
    try:
        auth = netrc.netrc(str(netrc_path)).authenticators(host)
    except (OSError, netrc.NetrcParseError):
        return None
    if auth is None:
        return None
    login, _, password = auth
    token = base64.b64encode(f"{login}:{password}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def main() -> int:
    lock_path = Path(sys.argv[1] if len(sys.argv) > 1 else "uv.lock")
    index = os.environ.get("UV_DEFAULT_INDEX", "").strip()
    index_host = urlparse(index).hostname
    if not index_host:
        return 0

    urls = [url for url in _artifact_urls(lock_path) if urlparse(url).hostname == index_host]
    if not urls:
        return 0

    url = urls[0]
    request = urllib.request.Request(url, method="GET", headers={"Range": "bytes=0-0"})
    auth_header = _basic_auth_for(index_host)
    if auth_header:
        request.add_header("Authorization", auth_header)

    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            return 0 if 200 <= response.status < 400 else 1
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        print(f"Mirror artifact preflight failed for {url}: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
