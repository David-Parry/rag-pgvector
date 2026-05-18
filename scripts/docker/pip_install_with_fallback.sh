#!/usr/bin/env sh
# pip install -r with optional private mirror, falling back to public PyPI.
set -eu

REQ_FILE="${1:?requirements file path is required}"

if [ -s /run/secrets/netrc ]; then
  install -m 600 /run/secrets/netrc /root/.netrc
fi

# Host global pip.ini / pip.conf (Windows: %APPDATA%\pip\pip.ini) mounted as a secret.
# Installed as Linux site config so `pip install` uses index-url, trusted-host, etc.
if [ -s /run/secrets/pip_config ]; then
  echo "Using BuildKit secret pip_config as /etc/pip.conf for pip index and related settings." >&2
  install -m 644 /run/secrets/pip_config /etc/pip.conf
fi

PIP_IDX="${PIP_INDEX_URL:-}"
if [ -z "${PIP_IDX}" ] && [ -s /run/secrets/pip_index_url ]; then
  PIP_IDX="$(tr -d '\r\n' < /run/secrets/pip_index_url)"
fi
# Backward compatibility: same secret file layout as older uv-based builds.
if [ -z "${PIP_IDX}" ] && [ -s /run/secrets/uv_default_index ]; then
  PIP_IDX="$(tr -d '\r\n' < /run/secrets/uv_default_index)"
fi

if [ -z "${PIP_IDX}" ] && [ -f /etc/pip.conf ]; then
  PIP_IDX="$(python3 -m pip config get global.index-url 2>/dev/null | tr -d '\r\n' || true)"
fi

if [ -s /run/secrets/ssl_cert_bundle ]; then
  echo "Using Docker build CA bundle for package downloads." >&2
  cat /run/secrets/ssl_cert_bundle >> /etc/ssl/certs/ca-certificates.crt
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

export PIP_DISABLE_PIP_VERSION_CHECK=1
export PIP_NO_CACHE_DIR=1
export PIP_RETRIES="${PIP_RETRIES:-10}"
export PIP_TIMEOUT="${PIP_TIMEOUT:-120}"

MIRROR_ENABLED=0
if [ -n "${PIP_IDX}" ]; then
  MIRROR_ENABLED=1
  export PIP_INDEX_URL="${PIP_IDX}"
  export PIP_INDEX_URL="$(python3 scripts/docker/prepare_artifactory_for_pip.py)"
  if [ ! -s /root/.netrc ] && echo "${PIP_IDX}" | grep -q '@'; then
    echo "Mirror URL has credentials but .netrc is missing; credentials may not apply." >&2
  fi
fi

python3 -m venv /workspace/.venv
# shellcheck disable=SC1091
. /workspace/.venv/bin/activate
python -m pip install --upgrade pip setuptools wheel

install_reqs() {
  attempt=1
  max_attempts="${PIP_INSTALL_RETRIES:-6}"
  while true; do
    python -m pip install -r "${REQ_FILE}"
    status="$?"
    if [ "${status}" -eq 0 ] || [ "${attempt}" -ge "${max_attempts}" ]; then
      return "${status}"
    fi
    echo "pip install failed; retrying (${attempt}/${max_attempts})..." >&2
    sleep "$((attempt * 2))"
    attempt="$((attempt + 1))"
  done
}

set +e
install_reqs
PIP_STATUS="$?"
set -e

if [ "${PIP_STATUS}" -ne 0 ] && [ "${MIRROR_ENABLED}" = "1" ]; then
  echo "Mirror install failed; retrying with public PyPI (no PIP_INDEX_URL)." >&2
  unset PIP_INDEX_URL
  MIRROR_ENABLED=0
  set +e
  install_reqs
  PIP_STATUS="$?"
  set -e
fi

if [ "${PIP_STATUS}" -ne 0 ]; then
  if [ "${MIRROR_ENABLED}" = "0" ]; then
    echo "ERROR: public PyPI is unavailable from this Docker build environment." >&2
    echo "Set RAG_DOCKER_PIP_CONFIG_FILE (host pip.ini), RAG_PIP_INDEX_URL_FILE (or legacy RAG_UV_DEFAULT_INDEX_FILE), or RAG_DOCKER_NETRC_FILE for a working mirror." >&2
  fi
  exit "${PIP_STATUS}"
fi

# pipecat[webrtc] depends on opencv-python, whose wheel links libxcb/libGL — GUI libs
# absent from slim runtime images. Server-side voice bot never renders, so swap to
# opencv-python-headless. Skipped automatically when opencv-python isn't installed
# (e.g. vectorizer image).
if python -m pip show opencv-python >/dev/null 2>&1; then
  python -m pip uninstall -y opencv-python
  python -m pip install --no-deps opencv-python-headless
fi
