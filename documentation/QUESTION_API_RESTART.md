# Restart question-api (Kubernetes)

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
