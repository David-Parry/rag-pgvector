#!/usr/bin/env sh
# Sync one workspace package, preferring a configured private mirror and falling
# back to public PyPI when the mirror is missing or inaccessible.
set -eu

PACKAGE_NAME="${1:?package name is required}"

if [ -s /run/secrets/netrc ]; then
  install -m 600 /run/secrets/netrc /root/.netrc
fi

UV_IDX="${UV_DEFAULT_INDEX:-}"
if [ -s /run/secrets/uv_default_index ]; then
  UV_IDX="$(tr -d '\r\n' < /run/secrets/uv_default_index)"
fi

if [ -s /run/secrets/ssl_cert_bundle ]; then
  echo "Using Docker build CA bundle for package downloads." >&2
  cat /run/secrets/ssl_cert_bundle >> /etc/ssl/certs/ca-certificates.crt
  export SSL_CERT_FILE=/etc/ssl/certs/ca-certificates.crt
  export REQUESTS_CA_BUNDLE=/etc/ssl/certs/ca-certificates.crt
fi

export UV_CONCURRENT_DOWNLOADS="${UV_CONCURRENT_DOWNLOADS:-1}"

MIRROR_ENABLED=0
cp uv.lock uv.lock.public
python3 scripts/docker/rewrite_uv_lock_for_public_pypi.py uv.lock.public

if [ -n "${UV_IDX}" ]; then
  MIRROR_ENABLED=1
  export UV_DEFAULT_INDEX="${UV_IDX}"
  export UV_DEFAULT_INDEX="$(python3 scripts/docker/prepare_artifactory_for_uv.py)"

  if [ ! -s /root/.netrc ]; then
    echo "Mirror credentials are not available; using public PyPI." >&2
    cp uv.lock.public uv.lock
    unset UV_DEFAULT_INDEX
    MIRROR_ENABLED=0
  else
    python3 scripts/docker/rewrite_uv_lock_for_mirror.py uv.lock
    if ! python3 scripts/docker/check_uv_lock_artifact_access.py uv.lock; then
      echo "Mirror is not accessible; using public PyPI." >&2
      cp uv.lock.public uv.lock
      unset UV_DEFAULT_INDEX
      MIRROR_ENABLED=0
    fi
  fi
fi

if [ "${MIRROR_ENABLED}" = "0" ]; then
  echo "Using public PyPI for package downloads." >&2
  cp uv.lock.public uv.lock
fi

sync_package() {
  attempt=1
  max_attempts="${UV_SYNC_RETRIES:-6}"
  while true; do
    uv sync --package "${PACKAGE_NAME}" --frozen --no-dev
    status="$?"
    if [ "${status}" -eq 0 ] || [ "${attempt}" -ge "${max_attempts}" ]; then
      return "${status}"
    fi
    echo "uv sync failed; retrying (${attempt}/${max_attempts})..." >&2
    sleep "$((attempt * 2))"
    attempt="$((attempt + 1))"
  done
}

set +e
sync_package
UV_STATUS="$?"
set -e

if [ "${UV_STATUS}" -ne 0 ] && [ "${MIRROR_ENABLED}" = "1" ]; then
  echo "Mirror install failed; retrying with public PyPI." >&2
  cp uv.lock.public uv.lock
  unset UV_DEFAULT_INDEX
  MIRROR_ENABLED=0
  set +e
  sync_package
  UV_STATUS="$?"
  set -e
fi

rm -f uv.lock.public

if [ "${UV_STATUS}" -ne 0 ]; then
  if [ "${MIRROR_ENABLED}" = "0" ]; then
    echo "ERROR: public PyPI is unavailable from this Docker build environment." >&2
    echo "Set RAG_UV_DEFAULT_INDEX_FILE and RAG_DOCKER_NETRC_FILE for a working mirror, or retry when the network/proxy stops returning errors." >&2
  fi
  exit "${UV_STATUS}"
fi
