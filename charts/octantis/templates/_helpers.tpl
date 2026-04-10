{{/*
Expand the name of the chart.
*/}}
{{- define "octantis.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "octantis.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "octantis.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels
*/}}
{{- define "octantis.labels" -}}
helm.sh/chart: {{ include "octantis.chart" . }}
{{ include "octantis.selectorLabels" . }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "octantis.selectorLabels" -}}
app.kubernetes.io/name: {{ include "octantis.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Octantis image tag: use values tag, fallback to Chart appVersion.
*/}}
{{- define "octantis.imageTag" -}}
{{- .Values.octantis.image.tag | default .Chart.AppVersion }}
{{- end }}

{{/*
Secret name resolver for a given secret key (e.g. "anthropicApiKey").
Priority: existingSecret > externalsecret > create
*/}}
{{- define "octantis.secretName" -}}
{{- $secret := index .context.Values.secrets .key -}}
{{- if $secret.existingSecret -}}
{{- $secret.existingSecret -}}
{{- else if $secret.externalsecret.create -}}
{{- printf "%s-%s" (include "octantis.fullname" .context) .key -}}
{{- else if $secret.create -}}
{{- printf "%s-%s" (include "octantis.fullname" .context) .key -}}
{{- end -}}
{{- end }}

{{/*
Determine if a secret is configured (any mode active).
*/}}
{{- define "octantis.secretConfigured" -}}
{{- $secret := index .context.Values.secrets .key -}}
{{- or $secret.create $secret.existingSecret $secret.externalsecret.create -}}
{{- end }}

{{/*
Grafana MCP URL: in-chart component takes precedence over external URL.
*/}}
{{- define "octantis.grafanaMcpUrl" -}}
{{- if .Values.grafanaMcp.enabled -}}
{{- printf "http://%s-grafana-mcp:%d/sse" (include "octantis.fullname" .) (int .Values.grafanaMcp.port) -}}
{{- else if .Values.octantis.externalMcp.grafanaUrl -}}
{{- .Values.octantis.externalMcp.grafanaUrl -}}
{{- end -}}
{{- end }}

{{/*
K8s MCP URL: in-chart component takes precedence over external URL.
*/}}
{{- define "octantis.k8sMcpUrl" -}}
{{- if .Values.k8sMcp.enabled -}}
{{- printf "http://%s-k8s-mcp:%d/sse" (include "octantis.fullname" .) (int .Values.k8sMcp.port) -}}
{{- else if .Values.octantis.externalMcp.k8sUrl -}}
{{- .Values.octantis.externalMcp.k8sUrl -}}
{{- end -}}
{{- end }}

{{/*
Check if any MCP is configured.
*/}}
{{- define "octantis.mcpConfigured" -}}
{{- or .Values.grafanaMcp.enabled .Values.k8sMcp.enabled .Values.octantis.externalMcp.grafanaUrl .Values.octantis.externalMcp.k8sUrl .Values.octantis.externalMcp.dockerUrl .Values.octantis.externalMcp.awsUrl -}}
{{- end }}

{{/*
Check if any ExternalSecret is enabled.
*/}}
{{- define "octantis.anyExternalSecret" -}}
{{- $result := false -}}
{{- range $key, $val := .Values.secrets -}}
{{- if $val.externalsecret.create -}}
{{- $result = true -}}
{{- end -}}
{{- end -}}
{{- $result -}}
{{- end }}

{{/*
ServiceAccount name for Octantis.
*/}}
{{- define "octantis.serviceAccountName" -}}
{{- if .Values.octantis.serviceAccount.create }}
{{- default (printf "%s-octantis" (include "octantis.fullname" .)) .Values.octantis.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.octantis.serviceAccount.name }}
{{- end }}
{{- end }}

{{/*
ServiceAccount name for K8s MCP.
*/}}
{{- define "octantis.k8sMcp.serviceAccountName" -}}
{{- if .Values.k8sMcp.serviceAccount.create }}
{{- default (printf "%s-k8s-mcp" (include "octantis.fullname" .)) .Values.k8sMcp.serviceAccount.name }}
{{- else }}
{{- default "default" .Values.k8sMcp.serviceAccount.name }}
{{- end }}
{{- end }}
