# Python tooling (pip and setuptools)

The monorepo uses **pip** against **PyPI** (or your corporate mirror) and **setuptools** as the PEP 517 build backend for `libs/rag-core`, `vectorizer`, `question-api`, and `evals`.

## Local setup

From the repository root:

```bash
python -m venv .venv
.venv\Scripts\pip install -r requirements\requirements-dev.txt
```

On macOS or Linux, use `.venv/bin/pip` and `.venv/bin/pytest` instead.

## Pinning dependencies

Input files live under `requirements/` (`*.in`). Regenerate install lists with [pip-tools](https://pip-tools.readthedocs.io/):

```bash
pip install pip-tools
pip-compile requirements/docker-vectorizer.in -o requirements/docker-vectorizer.txt
pip-compile requirements/docker-question-api.in -o requirements/docker-question-api.txt
pip-compile requirements/requirements-dev.in -o requirements/requirements-dev.txt
```

The committed `requirements/docker-*.txt` files list **`-e ./libs/rag-core`** before **`-e ./vectorizer`** / **`-e ./question-api`** so the shared library is installed from repo-root paths; member packages declare **`rag-core==0.1.0`** so pip reuses that editable (a lone `file:../libs/rag-core` URL in `pyproject.toml` is mis-resolved to `/libs/rag-core` during some Docker installs). Fully pinned output from `pip-compile` is recommended for reproducible builds.

## Building wheels

Install the PyPA **`build`** package and run from a package directory:

```bash
pip install build
cd question-api
python -m build
```

This uses `[build-system]` (`setuptools.build_meta`) declared in that package's `pyproject.toml`.
