# Docker builds: PyPI mirror (JFrog Artifactory) and TLS

On some networks, `uv sync` inside the image build fails when downloading wheels from `files.pythonhosted.org` with TLS errors (for example `invalid peer certificate: UnknownIssuer`). That usually means TLS interception or a policy that requires pulling Python packages through an internal mirror such as JFrog Artifactory.

The `vectorizer` and `question-api` Dockerfiles support:

- **`UV_DEFAULT_INDEX`** — PEP 503 simple API URL for your Artifactory virtual PyPI repository (replaces public PyPI for that build).
- **Lockfile rewrite** — `uv.lock` stores absolute `https://files.pythonhosted.org/packages/...` download URLs. Setting `UV_DEFAULT_INDEX` alone does not change those URLs, so the builder runs `scripts/docker/rewrite_uv_lock_for_mirror.py` to point artifacts and registry entries at Artifactory. Wheel paths follow JFrog’s layout: `.../api/pypi/<repo>/packages/packages/<hash>/...` (double `packages`). If you see HTTP 404, confirm repository key and virtual/remote configuration with your Artifactory admin.
- **Optional `.netrc`** — uv can read JFrog credentials from a standard netrc file (see [uv JFrog integration](https://docs.astral.sh/uv/guides/integration/jfrog/)).
- **Optional `SSL_CERT_FILE`** — PEM bundle for TLS if the mirror uses a private CA or you must trust an enterprise root (must include every issuer in the chain uv needs; combining public roots with your corporate root is often required).

Avoid sharing Docker build logs if your index URL contains credentials. Prefer `.netrc` plus an uncredentialled URL in `uv-default-index.txt`, or rotate tokens if a log may have captured them.

### Credentials in `uv-default-index.txt` (automatic `.netrc`)

If your secret file uses a URL with `https://user:token@host/.../simple`, the Docker builder runs `scripts/docker/prepare_artifactory_for_uv.py`: it appends a `machine` block to `/root/.netrc` and sets `UV_DEFAULT_INDEX` to the **same URL without userinfo**. That helps tools (including uv) send Basic Auth on **wheel** URLs under `.../packages/packages/...`, not only on the simple index.

You can still set `RAG_DOCKER_NETRC_FILE` instead; the builder installs that file first, then merges any credentials parsed from the index URL.

### HTTP 404 on wheels

If URLs look like `.../api/pypi/<repo>/packages/packages/...` but Artifactory still returns 404, verify read access to the virtual repository, that the remote repository can reach upstream PyPI to populate the cache, and try a lower concurrency: `UV_CONCURRENT_DOWNLOADS=2` is the default during mirror builds (some Artifactory setups mis-handle concurrent unauthenticated attempts; see [astral-sh/uv#17485](https://github.com/astral-sh/uv/issues/17485)).

## Quick start (BuildKit secrets, recommended)

Create two single-line files (do not commit them). Use the simple index URL your Artifactory admin documents — typical shape:

`https://<host>/artifactory/api/pypi/<repository-name>/simple`

**Option A — credentials in the index URL (basic auth)**

`uv-default-index.txt` (one line, no trailing newline beyond what your editor adds):

```text
https://<username>:<identity-token>@acadartifactory.jfrog.io/artifactory/api/pypi/<repo>/simple
```

Build:

```bash
export RAG_UV_DEFAULT_INDEX_FILE="$(pwd)/uv-default-index.txt"
bash scripts/docker-desktop-up.sh
```

**Option B — `.netrc` for authentication**

`uv-default-index.txt` holds only the HTTPS simple URL (no userinfo). `netrc` contains machine, login, and password per JFrog’s uv guide.

```bash
export RAG_UV_DEFAULT_INDEX_FILE="$(pwd)/uv-default-index.txt"
export RAG_DOCKER_NETRC_FILE="$HOME/.netrc"
bash scripts/docker-desktop-up.sh
```

On Windows PowerShell from the repo root (adjust paths):

```powershell
$env:RAG_UV_DEFAULT_INDEX_FILE = "$PWD\uv-default-index.txt"
$env:RAG_DOCKER_NETRC_FILE = "$HOME\_netrc"
.\scripts\ps\Docker-Desktop-Up.ps1
```

If your Windows `pip.ini` already contains the Artifactory `index-url`, use the helper to create the BuildKit secret automatically without printing the index URL:

```powershell
.\scripts\ps\env_var_artifactory.ps1
```

**Optional corporate CA bundle** (PEM file trusted by uv for the whole build):

```bash
export RAG_DOCKER_SSL_CERT_BUNDLE_FILE="$(pwd)/combined-ca-bundle.pem"
```

## Direct `docker build`

Use the same secret ids as in the Dockerfiles:

```bash
docker build \
  --secret id=uv_default_index,src=./uv-default-index.txt \
  --secret id=netrc,src="$HOME/.netrc" \
  --secret id=ssl_cert_bundle,src=./combined-ca-bundle.pem \
  -t rag-pgvector/vectorizer:0.1.0 \
  -f vectorizer/Dockerfile .
```

Omit any `--secret` you do not need.

## Less secure: build-arg

`UV_DEFAULT_INDEX` can be passed as a build-arg (credentials may appear in build history). The helper scripts honor `RAG_DOCKER_UV_DEFAULT_INDEX`.

## Local `uv sync` on the host

The same environment variables uv documents apply outside Docker: `UV_DEFAULT_INDEX` and, for named indexes in `pyproject.toml`, `UV_INDEX_<NAME>_USERNAME` / `UV_INDEX_<NAME>_PASSWORD`. See [uv package indexes](https://docs.astral.sh/uv/concepts/indexes/) and [JFrog](https://docs.astral.sh/uv/guides/integration/jfrog/).

## Environment variables (helper scripts)

| Variable | Purpose |
|----------|---------|
| `RAG_UV_DEFAULT_INDEX_FILE` | Path to a file whose contents set `UV_DEFAULT_INDEX` during the build (BuildKit secret `uv_default_index`). |
| `RAG_DOCKER_NETRC_FILE` | Path to `.netrc` installed as `/root/.netrc` for the `uv sync` step only (BuildKit secret `netrc`). |
| `RAG_DOCKER_SSL_CERT_BUNDLE_FILE` | PEM bundle for `SSL_CERT_FILE` during `uv sync` (BuildKit secret `ssl_cert_bundle`). |
| `RAG_DOCKER_UV_DEFAULT_INDEX` | Pass-through to `--build-arg UV_DEFAULT_INDEX` (avoid for secrets). |

Replace `<repo>` and hostnames with values from your Artifactory PyPI virtual repository configuration.

## Build backend (`hatchling` / `uv_build`)

Workspace packages in this repository declare `[build-system]` with **Astral `uv_build`**, not Hatchling. The `uv` used in Docker (`ghcr.io/astral-sh/uv`) embeds a compatible `uv_build`, so the builder typically does **not** need to download a separate build-backend wheel from your mirror.

If you still see resolution errors for a third-party build backend on an older branch, either ensure your virtual repository proxies upstream PyPI for build dependencies, or set an additional index (for example `UV_EXTRA_INDEX_URL`) per [uv package indexes](https://docs.astral.sh/uv/concepts/indexes/) if your security policy allows it.
