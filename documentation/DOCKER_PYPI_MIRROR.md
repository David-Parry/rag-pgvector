# Corporate PyPI mirror and TLS for Docker builds (pip)

On some networks, `pip install` inside the image build fails when downloading wheels from `https://pypi.org/simple` or `files.pythonhosted.org` with TLS errors (for example `invalid peer certificate: UnknownIssuer`). That usually means TLS interception or a policy that requires pulling Python packages through an internal mirror such as JFrog Artifactory.

## What this repository does

- **`/etc/pip.conf` in the builder** — When BuildKit secret **`pip_config`** is provided (`RAG_DOCKER_PIP_CONFIG_FILE`), the install script copies your host **`pip.ini`** / **`pip.conf`** there so `pip install` uses the same **`index-url`**, **`trusted-host`**, **`extra-index-url`**, and related settings as a typical global pip config.
- **`PIP_INDEX_URL`** — PEP 503 simple API URL for your Artifactory virtual PyPI repository (replaces public PyPI for that build). The Docker builder may also read legacy **`UV_DEFAULT_INDEX`** / `RAG_DOCKER_UV_DEFAULT_INDEX` and map them to the same behavior.
- **`.netrc`** — When the index URL contains `https://user:token@host/.../simple`, the Docker builder runs `scripts/docker/prepare_artifactory_for_pip.py`: it appends a `machine` block to `/root/.netrc` and prints the **same URL without userinfo** so `PIP_INDEX_URL` does not embed credentials in the environment while pip still authenticates to the mirror host.
- **Optional PEM bundle** — `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` point at the system CA bundle plus any corporate root appended from the `ssl_cert_bundle` BuildKit secret.

Avoid sharing Docker build logs if your index URL contains credentials. Prefer `.netrc` plus an uncredentialled URL in `pip-index-url.txt`, or rotate tokens if a log may have captured them.

### Credentials in `pip-index-url.txt` (automatic `.netrc`)

If your secret file uses a URL with `https://user:token@host/.../simple`, the Docker builder runs `prepare_artifactory_for_pip.py`: it appends a `machine` block to `/root/.netrc` and sets `PIP_INDEX_URL` to the **same URL without userinfo**. That helps pip send Basic Auth on wheel URLs under the mirror host, not only on the simple index.

## BuildKit secrets (recommended)

### Full host `pip.ini` as `/etc/pip.conf` (recommended when you already use global pip config)

If your Artifactory URL, `trusted-host`, `extra-index-url`, or other pip settings live in your **user-level pip.ini** (Windows: `%APPDATA%\pip\pip.ini`; Linux/macOS: `~/.config/pip/pip.conf` or `~/.pip/pip.conf`), mount that file into the build as secret **`pip_config`**. The install script copies it to **`/etc/pip.conf`** inside the builder so `pip install` uses the same policy as your host.

```bash
export DOCKER_BUILDKIT=1
export RAG_DOCKER_PIP_CONFIG_FILE="${APPDATA:-$HOME}/pip/pip.ini"   # adjust for your OS
export RAG_DOCKER_NETRC_FILE="$(pwd)/.netrc"   # optional; if credentials are not embedded in index-url
bash scripts/docker-desktop-up.sh
```

PowerShell (typical Windows global file):

```powershell
$env:DOCKER_BUILDKIT = '1'
$env:RAG_DOCKER_PIP_CONFIG_FILE = Join-Path $env:APPDATA 'pip\pip.ini'
$env:RAG_DOCKER_NETRC_FILE = "$PWD\.netrc"   # optional
.\scripts\ps\Docker-Desktop-Up.ps1
```

`.\scripts\ps\env_var_artifactory.ps1` discovers `%APPDATA%\pip\pip.ini` when it contains `index-url` and sets `RAG_DOCKER_PIP_CONFIG_FILE` automatically (unless you already set a one-line `RAG_PIP_INDEX_URL_FILE`).

Precedence inside the builder: **`PIP_INDEX_URL` / `pip_index_url` / `uv_default_index`** are applied first; if none are set, the script reads **`global.index-url`** from `/etc/pip.conf` (after copying `pip_config`) for mirror detection and optional `.netrc` merging when the URL contains userinfo.

### One-line index URL file

Create a one-line file with your PEP 503 simple URL (with or without userinfo, per your Artifactory policy):

`pip-index-url.txt` (one line):

```
https://acadartifactory.jfrog.io/artifactory/api/pypi/npm/simple
```

Bash:

```bash
export DOCKER_BUILDKIT=1
export RAG_PIP_INDEX_URL_FILE="$(pwd)/pip-index-url.txt"
export RAG_DOCKER_NETRC_FILE="$(pwd)/.netrc"   # optional; only if you do not embed userinfo in the URL
bash scripts/docker-desktop-up.sh
```

PowerShell:

```powershell
$env:DOCKER_BUILDKIT = '1'
$env:RAG_PIP_INDEX_URL_FILE = "$PWD\pip-index-url.txt"
$env:RAG_DOCKER_NETRC_FILE = "$PWD\.netrc"   # optional
.\scripts\ps\Docker-Desktop-Up.ps1
```

**Optional corporate CA bundle** (PEM file trusted by pip for the whole build):

```bash
export RAG_DOCKER_SSL_CERT_BUNDLE_FILE="$(pwd)/corp-ca-bundle.pem"
```

## Manual `docker build`

```bash
docker build \
  --secret id=pip_config,src="$HOME/.config/pip/pip.conf" \
  --secret id=pip_index_url,src=./pip-index-url.txt \
  --secret id=netrc,src=./.netrc \
  --secret id=ssl_cert_bundle,src=./corp-ca-bundle.pem \
  -f vectorizer/Dockerfile .
```

You can pass **`pip_config` alone** when `index-url` (and any `trusted-host` / `extra-index-url`) are defined in that file.

`PIP_INDEX_URL` can be passed as `--build-arg` (credentials may appear in build history). The helper scripts honor `RAG_DOCKER_PIP_INDEX_URL` and legacy `RAG_DOCKER_UV_DEFAULT_INDEX`.

## Local `pip install` on the host

Use the same index as in Docker when needed:

```bash
export PIP_INDEX_URL="https://your-mirror/.../simple"
python -m pip install -r requirements/requirements-dev.txt
```

See [pip user guide: configuration](https://pip.pypa.io/en/stable/topics/configuration/) and your mirror vendor’s documentation for authentication.

## Environment variables (summary)

| Variable | Purpose |
|----------|---------|
| `RAG_DOCKER_PIP_CONFIG_FILE` | Path to your host **pip.ini** / **pip.conf** mounted as BuildKit secret `pip_config` and installed as `/etc/pip.conf` for the `pip install` step. |
| `RAG_PIP_INDEX_URL_FILE` | Path to a file whose contents set `PIP_INDEX_URL` during the build (BuildKit secret `pip_index_url`). |
| `RAG_UV_DEFAULT_INDEX_FILE` | **Legacy:** same as above but mounts secret `uv_default_index` (still read by `pip_install_with_fallback.sh`). |
| `RAG_DOCKER_NETRC_FILE` | Path to `.netrc` installed as `/root/.netrc` for the `pip install` step only (BuildKit secret `netrc`). |
| `RAG_DOCKER_SSL_CERT_BUNDLE_FILE` | PEM bundle appended to the system trust store during the install step (BuildKit secret `ssl_cert_bundle`). |
| `RAG_DOCKER_PIP_INDEX_URL` | Pass-through to `--build-arg PIP_INDEX_URL` (avoid for secrets). |
| `RAG_DOCKER_UV_DEFAULT_INDEX` | **Legacy:** same pass-through intent as `PIP_INDEX_URL`. |

## Build backend (setuptools)

Workspace packages declare `[build-system]` with **setuptools** (`setuptools.build_meta`). The default `python:3.12-slim-bookworm` image includes enough tooling for `pip` to install build dependencies from your mirror or from PyPI.

If resolution errors reference a missing build dependency on an air-gapped mirror, ensure your virtual repository proxies upstream PyPI for build backends, or set `PIP_EXTRA_INDEX_URL` if your security policy allows it.

## Optional: PyPA `build`

To produce sdists or wheels from a clean tree:

```bash
pip install build
cd question-api && python -m build
```

This invokes the package’s declared `[build-system]` (setuptools).
