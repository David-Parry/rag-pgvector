#requires -Version 5.1
<#
.SYNOPSIS
  Verify Docker Desktop Kubernetes is reachable and build local images.

.DESCRIPTION
  Parallel to scripts/docker-desktop-up.sh — Docker Desktop shares the daemon
  with Kubernetes; plain docker build is enough.

.NOTES
  Enable Kubernetes in Docker Desktop before running.

.EXAMPLE
  .\Docker-Desktop-Up.ps1
#>
Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
. "$PSScriptRoot/_Common.ps1"

$NAMESPACE = if ($env:NAMESPACE) { $env:NAMESPACE } else { 'rag' }
$TAG = if ($env:TAG) { $env:TAG } else { '0.1.0' }
$KUBE_CONTEXT = if ($env:KUBE_CONTEXT) { $env:KUBE_CONTEXT } else { 'docker-desktop' }

$ROOT_DIR = Get-RagRepoRoot
Set-Location $ROOT_DIR

Test-RagCommand docker 'Install Docker Desktop for Windows.'
Test-RagCommand kubectl 'Install kubectl (winget install Kubernetes.kubectl).'

function Import-RagImagesToKubernetesContainerd {
    param(
        [Parameter(Mandatory)]
        [string[]]$Images
    )

    $runtime = kubectl get node -o jsonpath='{.items[0].status.nodeInfo.containerRuntimeVersion}'
    if ($runtime -notlike 'containerd://*') {
        return
    }

    Write-Host ''
    Write-Host 'Importing local images into Docker Desktop Kubernetes containerd...'

    $nodeInfo = kubectl get node -o json | ConvertFrom-Json
    $debugImage = $nodeInfo.items[0].status.images |
        ForEach-Object { $_.names } |
        Where-Object { $_ -like 'docker.io/kindest/kindnetd:*' } |
        Select-Object -First 1
    if (-not $debugImage) {
        Write-Error 'ERROR: could not find cached kindnetd image for the Docker Desktop image loader pod.'
        exit 1
    }

    $manifest = @'
apiVersion: v1
kind: Pod
metadata:
  name: rag-image-loader
spec:
  restartPolicy: Never
  hostPID: true
  nodeName: desktop-control-plane
  tolerations:
    - operator: Exists
  containers:
    - name: rag-image-loader
      image: __DEBUG_IMAGE__
      command: ["/host/usr/sbin/chroot", "/host", "/bin/sleep", "3600"]
      securityContext:
        privileged: true
      volumeMounts:
        - name: host-root
          mountPath: /host
  volumes:
    - name: host-root
      hostPath:
        path: /
'@
    $manifest = $manifest.Replace('__DEBUG_IMAGE__', $debugImage)

    kubectl delete pod rag-image-loader --ignore-not-found | Out-Null
    $manifest | kubectl apply -f - | Out-Null
    kubectl wait --for=condition=Ready pod/rag-image-loader --timeout=30s | Out-Null

    try {
        $imageArgs = $Images -join ' '
        $importCommand = "docker save $imageArgs | kubectl exec -i rag-image-loader -- /host/usr/sbin/chroot /host /usr/local/bin/ctr -n k8s.io images import -"
        & cmd.exe /d /s /c $importCommand
        if ($LASTEXITCODE -ne 0) {
            exit $LASTEXITCODE
        }
    }
    finally {
        kubectl delete pod rag-image-loader --ignore-not-found | Out-Null
    }
}

Write-Host 'Checking Docker Desktop Kubernetes context...'
$contextNames = @(kubectl config get-contexts -o name 2>$null | ForEach-Object { $_.Trim() } | Where-Object { $_ })
if ($contextNames -notcontains $KUBE_CONTEXT) {
    Write-Error @"
ERROR: kube context '$KUBE_CONTEXT' was not found.

Enable Kubernetes in Docker Desktop:
  Docker Desktop -> Settings -> Kubernetes -> Enable Kubernetes -> Apply & restart

Then re-run this script.
"@
    exit 1
}

kubectl config use-context $KUBE_CONTEXT | Out-Null

if ((Invoke-RagKubectlProbe -Arguments @('version', '--request-timeout=5s')) -ne 0) {
    Write-Error "ERROR: cannot reach the '$KUBE_CONTEXT' API server. Is Docker Desktop running?"
    exit 1
}

if (-not (Test-RagKubernetesNamespaceExists -Namespace $NAMESPACE)) {
    kubectl create namespace $NAMESPACE
    if ($LASTEXITCODE -ne 0) {
        exit $LASTEXITCODE
    }
}

# Optional corporate PyPI / TLS — see documentation/DOCKER_PYPI_MIRROR.md
$pyAppBuildArgs = @()
$pipIndexArg = $env:RAG_DOCKER_PIP_INDEX_URL
if (-not $pipIndexArg) {
    $pipIndexArg = $env:RAG_DOCKER_UV_DEFAULT_INDEX
}
if ($pipIndexArg) {
    $pyAppBuildArgs += '--build-arg', "PIP_INDEX_URL=$pipIndexArg"
}
if ($env:RAG_PIP_INDEX_URL_FILE) {
    $pyAppBuildArgs += '--secret', "id=pip_index_url,src=$($env:RAG_PIP_INDEX_URL_FILE)"
}
if ($env:RAG_UV_DEFAULT_INDEX_FILE) {
    $pyAppBuildArgs += '--secret', "id=uv_default_index,src=$($env:RAG_UV_DEFAULT_INDEX_FILE)"
}
if ($env:RAG_DOCKER_NETRC_FILE) {
    $pyAppBuildArgs += '--secret', "id=netrc,src=$($env:RAG_DOCKER_NETRC_FILE)"
}
if ($env:RAG_DOCKER_SSL_CERT_BUNDLE_FILE) {
    $pyAppBuildArgs += '--secret', "id=ssl_cert_bundle,src=$($env:RAG_DOCKER_SSL_CERT_BUNDLE_FILE)"
}
if ($env:RAG_DOCKER_PIP_CONFIG_FILE) {
    $pyAppBuildArgs += '--secret', "id=pip_config,src=$($env:RAG_DOCKER_PIP_CONFIG_FILE)"
}

Write-Host ''
Write-Host 'Building rag-pgvector/postgres:17 ...'
docker build -t 'rag-pgvector/postgres:17' (Join-Path $ROOT_DIR 'infra/docker/postgres-pgvector')
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host "Building rag-pgvector/vectorizer:${TAG} ..."
docker build @pyAppBuildArgs -t "rag-pgvector/vectorizer:${TAG}" -f (Join-Path $ROOT_DIR 'vectorizer/Dockerfile') $ROOT_DIR
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

Write-Host ''
Write-Host "Building rag-pgvector/question-api:${TAG} ..."
docker build @pyAppBuildArgs -t "rag-pgvector/question-api:${TAG}" -f (Join-Path $ROOT_DIR 'question-api/Dockerfile') $ROOT_DIR
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

$builtImages = @(
    'rag-pgvector/postgres:17',
    "rag-pgvector/vectorizer:${TAG}",
    "rag-pgvector/question-api:${TAG}"
)
Import-RagImagesToKubernetesContainerd -Images $builtImages

Write-Host @"

Cluster ready (Docker Desktop Kubernetes).
  context:    $KUBE_CONTEXT
  namespace:  $NAMESPACE
  images:     rag-pgvector/postgres:17, rag-pgvector/vectorizer:${TAG}, rag-pgvector/question-api:${TAG}

Images are built locally and imported into Docker Desktop Kubernetes when it uses
containerd, so no registry push is required.

Next: .\scripts\ps\Helm-Install.ps1   or   .\scripts\ps\Rag.ps1 helm-install
"@
