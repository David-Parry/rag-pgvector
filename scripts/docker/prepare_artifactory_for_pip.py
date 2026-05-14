"""Ensure JFrog credentials apply to artifact downloads, not only the simple index.

pip may not attach Basic Auth from a credentialed ``PIP_INDEX_URL`` to every wheel
URL. A ``~/.netrc`` entry for the Artifactory host causes credentials to be sent on
requests to that host.

Reads ``PIP_INDEX_URL``, or ``UV_DEFAULT_INDEX`` for backward compatibility. If the
URL contains HTTP userinfo, merges a ``machine`` block into ``PIP_NETRC_FILE`` (default
``/root/.netrc``) and prints the same URL **without** userinfo to stdout for the shell
to ``export PIP_INDEX_URL="$(…)"``.
"""

from __future__ import annotations

import os
from pathlib import Path
from urllib.parse import urlunparse, urlparse


def _append_netrc(path: Path, machine: str, login: str, password: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    parts: list[str] = []
    if path.is_file() and path.stat().st_size > 0:
        parts.append(path.read_text(encoding="utf-8").rstrip())
    parts.append(f"machine {machine}\nlogin {login}\npassword {password}\n")
    path.write_text("\n".join(parts).strip() + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _index_url() -> str:
    return (
        os.environ.get("PIP_INDEX_URL", "").strip()
        or os.environ.get("UV_DEFAULT_INDEX", "").strip()
    )


def main() -> int:
    raw = _index_url()
    if not raw:
        print("")
        return 0

    parsed = urlparse(raw)
    if not parsed.hostname:
        print(raw)
        return 0

    user = parsed.username
    passwd = parsed.password
    if user is None and passwd is None:
        print(raw)
        return 0

    login = user if user is not None else ""
    password = passwd if passwd is not None else ""

    host = parsed.hostname
    assert host is not None
    if parsed.port is not None and not (
        (parsed.scheme == "https" and parsed.port == 443)
        or (parsed.scheme == "http" and parsed.port == 80)
    ):
        clean_netloc = f"{host}:{parsed.port}"
    else:
        clean_netloc = host

    netrc_path = Path(os.environ.get("PIP_NETRC_FILE", "/root/.netrc"))
    _append_netrc(netrc_path, host, login, password)

    clean = urlunparse(
        (
            parsed.scheme,
            clean_netloc,
            parsed.path,
            parsed.params,
            parsed.query,
            parsed.fragment,
        )
    )
    print(clean)


if __name__ == "__main__":
    raise SystemExit(main())
