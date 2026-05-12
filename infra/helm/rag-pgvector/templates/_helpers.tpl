{{/*
Common helpers for rag-pgvector.
*/}}

{{- define "rag.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{- define "rag.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name (include "rag.name" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}

{{- define "rag.labels" -}}
app.kubernetes.io/name: {{ include "rag.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
{{- end -}}

{{- define "rag.componentLabels" -}}
{{ include "rag.labels" . }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{- define "rag.componentSelector" -}}
app.kubernetes.io/name: {{ include "rag.name" .root }}
app.kubernetes.io/instance: {{ .root.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end -}}

{{/*
Component-scoped resource name: <release>-<chart>-<component>.
Usage: include "rag.componentName" (dict "root" . "component" "vectorizer")
*/}}
{{- define "rag.componentName" -}}
{{- printf "%s-%s" (include "rag.fullname" .root) .component | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Resolve an image reference for an app component, falling back to the chart-wide
image registry/tag/pullPolicy when the per-component value is empty.
Usage: include "rag.image" (dict "root" . "component" .Values.vectorizer)
*/}}
{{- define "rag.image" -}}
{{- $registry := .root.Values.image.registry | default "" -}}
{{- $repo := .component.image.repository -}}
{{- $tag := default .root.Values.image.tag .component.image.tag -}}
{{- if $registry -}}{{ $registry }}{{- end -}}{{ $repo }}:{{ $tag }}
{{- end -}}

{{- define "rag.imagePullPolicy" -}}
{{- default .root.Values.image.pullPolicy .component.image.pullPolicy -}}
{{- end -}}

{{/*
Service account name (single SA shared by both apps so IRSA annotation is uniform).
*/}}
{{- define "rag.serviceAccountName" -}}
{{- printf "%s-app" (include "rag.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
DATABASE_URL pointing at the in-cluster postgres service.
Uses psycopg3 driver (postgresql+psycopg://) which both apps depend on.
*/}}
{{- define "rag.databaseUrl" -}}
{{- $svc := printf "%s-postgres" (include "rag.fullname" .) -}}
{{- printf "postgresql+psycopg://%s:%s@%s:%v/%s" .Values.postgres.auth.user .Values.postgres.auth.password $svc .Values.postgres.service.port .Values.postgres.auth.database -}}
{{- end -}}
