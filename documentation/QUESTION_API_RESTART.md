# Restart question-api (Kubernetes)

## Preferred update flow

Use the update scripts when you want to apply code, image, Helm value, or Secret
changes to existing RAG pods without tearing down the release:

```powershell
.\scripts\ps\Rag.ps1 update-rag-pods
```

```bash
bash scripts/update-rag-pods.sh
```

The update flow rebuilds local images, runs `helm upgrade --install` against the
existing release, and rollout-restarts the selected Deployment(s). It does not
run teardown, uninstall Helm, delete PVCs, or delete the namespace. By default it
rolls `question-api`, which is the pod affected by the Nova Sonic voice backend
feature.

Optional environment variables:

| Variable | Default | Purpose |
|----------|---------|---------|
| `UPDATE_COMPONENTS` | `question-api` | Comma-separated Deployment components to rollout restart, for example `question-api,vectorizer` |
| `UPDATE_SKIP_BUILD` | unset | Set to `1` to skip Docker image rebuild/import |
| `UPDATE_SKIP_HELM` | unset | Set to `1` to skip Helm upgrade |
| `UPDATE_SKIP_ROLLOUT` | unset | Set to `1` to skip rollout restart |

## When to use

Use this after changing `question-api` Python code **when the app runs as a Helm-deployed pod** (for example Docker Desktop Kubernetes). A rollout restart recreates pods with the same image tag; if you need **new code inside the image**, rebuild first (see below).

## PowerShell

From the repository root:

```powershell
cd scripts\ps
.\Rag.ps1 restart-question-api
```

Aliases: `restart-qa`, `restart-api`.

Or invoke the script directly:

```powershell
.\scripts\ps\Restart-QuestionApi.ps1
```

## Environment variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `NAMESPACE` | `rag` | Kubernetes namespace for the Helm release |
| `KUBE_CONTEXT` | (unset) | If set, `kubectl config use-context` is run before restart |
| `ROLLOUT_TIMEOUT` | `300s` | Passed to `kubectl rollout status --timeout=...` |

## New image contents

`kubectl rollout restart` alone does **not** rebuild Docker images. After code changes, rebuild and reload images into the cluster (for example `.\Rag.ps1 docker-up`), then either restart the deployment as above or upgrade the Helm release so pods pick up the new tag.

## Selection logic

The script finds Deployments with label `app.kubernetes.io/component=question-api`, matching the chart in `infra/helm/rag-pgvector`.
