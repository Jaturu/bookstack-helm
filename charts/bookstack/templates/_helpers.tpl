{{/* ===================================================================
     Names and labels
     =================================================================== */}}

{{- define "bookstack.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{- define "bookstack.fullname" -}}
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

{{- define "bookstack.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/* Common labels. Call with (dict "ctx" $ "component" "app") */}}
{{- define "bookstack.labels" -}}
helm.sh/chart: {{ include "bookstack.chart" .ctx }}
{{ include "bookstack.selectorLabels" . }}
app.kubernetes.io/version: {{ .ctx.Chart.AppVersion | quote }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
app.kubernetes.io/part-of: bookstack
{{- end }}

{{/* Pod template labels. Call with (dict "ctx" $ "component" "app")
     Only labels that stay the same across chart and app versions: any change
     to a pod template restarts its pods, so the chart and version labels stay
     on the Deployment and StatefulSet objects. Otherwise every chart upgrade
     would restart MariaDB even when nothing about it changed. */}}
{{- define "bookstack.podLabels" -}}
{{ include "bookstack.selectorLabels" . }}
app.kubernetes.io/managed-by: {{ .ctx.Release.Service }}
app.kubernetes.io/part-of: bookstack
{{- end }}

{{/* Selector labels. Call with (dict "ctx" $ "component" "app") */}}
{{- define "bookstack.selectorLabels" -}}
app.kubernetes.io/name: {{ include "bookstack.name" .ctx }}
app.kubernetes.io/instance: {{ .ctx.Release.Name }}
app.kubernetes.io/component: {{ .component }}
{{- end }}

{{/* ===================================================================
     Images
     Call with (dict "image" .Values.image "default" .Chart.AppVersion)
     digest wins over tag; tag falls back to "default".
     =================================================================== */}}

{{- define "bookstack.imageRef" -}}
{{- $tag := default .default .image.tag -}}
{{- if .image.digest -}}
{{- printf "%s@%s" .image.repository .image.digest -}}
{{- else -}}
{{- printf "%s:%s" .image.repository $tag -}}
{{- end -}}
{{- end }}

{{/* ===================================================================
     Resource names
     =================================================================== */}}

{{- define "bookstack.appKeySecretName" -}}
{{- default (printf "%s-app-key" (include "bookstack.fullname" .)) .Values.bookstack.appKey.existingSecret -}}
{{- end }}

{{- define "bookstack.pvcName" -}}
{{- default (printf "%s-data" (include "bookstack.fullname" .)) .Values.persistence.existingClaim -}}
{{- end }}

{{- define "bookstack.mariadb.fullname" -}}
{{- printf "%s-mariadb" (include "bookstack.fullname" .) | trunc 63 | trimSuffix "-" -}}
{{- end }}

{{- define "bookstack.mariadb.secretName" -}}
{{- default (include "bookstack.mariadb.fullname" .) .Values.mariadb.auth.existingSecret -}}
{{- end }}

{{/* ===================================================================
     Database wiring – single place that decides built-in vs external
     =================================================================== */}}

{{- define "bookstack.db.host" -}}
{{- if .Values.mariadb.enabled -}}
{{- include "bookstack.mariadb.fullname" . -}}
{{- else -}}
{{- .Values.externalDatabase.host -}}
{{- end -}}
{{- end }}

{{- define "bookstack.db.port" -}}
{{- if .Values.mariadb.enabled -}}3306{{- else -}}{{ .Values.externalDatabase.port }}{{- end -}}
{{- end }}

{{- define "bookstack.db.database" -}}
{{- if .Values.mariadb.enabled -}}{{ .Values.mariadb.auth.database }}{{- else -}}{{ .Values.externalDatabase.database }}{{- end -}}
{{- end }}

{{- define "bookstack.db.username" -}}
{{- if .Values.mariadb.enabled -}}{{ .Values.mariadb.auth.username }}{{- else -}}{{ .Values.externalDatabase.username }}{{- end -}}
{{- end }}

{{- define "bookstack.db.secretName" -}}
{{- if .Values.mariadb.enabled -}}{{ include "bookstack.mariadb.secretName" . }}{{- else -}}{{ .Values.externalDatabase.existingSecret }}{{- end -}}
{{- end }}

{{- define "bookstack.db.passwordKey" -}}
{{- if .Values.mariadb.enabled -}}{{ .Values.mariadb.auth.passwordKey }}{{- else -}}{{ .Values.externalDatabase.passwordKey }}{{- end -}}
{{- end }}

{{/* ===================================================================
     Generated secrets: reuse the in-cluster value if present, otherwise
     generate. Returns the base64-encoded value for a Secret's data field.
     Call with (dict "ctx" $ "name" <secret> "key" <key> "length" 32)
     =================================================================== */}}

{{- define "bookstack.secretValue" -}}
{{- $existing := lookup "v1" "Secret" .ctx.Release.Namespace .name -}}
{{- $data := dict -}}
{{- if $existing -}}{{- $data = default (dict) $existing.data -}}{{- end -}}
{{- if hasKey $data .key -}}
{{- index $data .key -}}
{{- else -}}
{{- randAlphaNum (int .length) | b64enc -}}
{{- end -}}
{{- end }}

{{/* ===================================================================
     Validation – fails the render with a clear message
     =================================================================== */}}

{{- define "bookstack.validate" -}}
{{- if not .Values.bookstack.appUrl -}}
{{- fail "bookstack.appUrl is required (e.g. https://wiki.example.com)" -}}
{{- end -}}
{{- if hasSuffix "/" .Values.bookstack.appUrl -}}
{{- fail "bookstack.appUrl must not end with a slash" -}}
{{- end -}}
{{- if lt (int .Values.bookstack.uploadLimitMB) 1 -}}
{{- fail "bookstack.uploadLimitMB must be a positive number of megabytes" -}}
{{- end -}}
{{- if regexMatch "(?m)^\\s*(upload_max_filesize|post_max_size)\\s*=" .Values.php.extraIni -}}
{{- fail "php.extraIni must not set upload_max_filesize or post_max_size – use bookstack.uploadLimitMB" -}}
{{- end -}}
{{- if ne (int .Values.replicaCount) 1 -}}
{{- fail "replicaCount must be 1 (ReadWriteOnce data volume, Recreate strategy)" -}}
{{- end -}}
{{- if not .Values.mariadb.enabled -}}
{{- if not .Values.externalDatabase.host -}}
{{- fail "externalDatabase.host is required when mariadb.enabled=false" -}}
{{- end -}}
{{- if not .Values.externalDatabase.existingSecret -}}
{{- fail "externalDatabase.existingSecret is required when mariadb.enabled=false" -}}
{{- end -}}
{{- end -}}
{{- $modes := list "local" "local_secure" "local_secure_restricted" "s3" -}}
{{- if not (has .Values.bookstack.storageType $modes) -}}
{{- fail (printf "bookstack.storageType must be one of %s (got %q)" (join ", " $modes) .Values.bookstack.storageType) -}}
{{- end -}}
{{- range $k := list "storageImageType" "storageAttachmentType" -}}
{{- $v := index $.Values.bookstack $k -}}
{{- if and $v (not (has $v $modes)) -}}
{{- fail (printf "bookstack.%s must be empty or one of %s (got %q)" $k (join ", " $modes) $v) -}}
{{- end -}}
{{- end -}}
{{- $types := list .Values.bookstack.storageType .Values.bookstack.storageImageType .Values.bookstack.storageAttachmentType -}}
{{- if has "s3" $types -}}
{{- if not .Values.bookstack.s3.bucket -}}
{{- fail "bookstack.s3.bucket is required when S3 storage is used" -}}
{{- end -}}
{{- if not .Values.bookstack.s3.existingSecret -}}
{{- fail "bookstack.s3.existingSecret is required when S3 storage is used" -}}
{{- end -}}
{{- end -}}
{{- end }}

{{/* ===================================================================
     php-fpm container env and mounts – shared by the migrate init
     container and the bookstack container so they never drift.
     =================================================================== */}}

{{/* Call with (dict "ctx" $ "useS3" <bool>) */}}
{{- define "bookstack.appEnv" -}}
{{- $v := .ctx.Values -}}
envFrom:
  - configMapRef:
      name: {{ include "bookstack.fullname" .ctx }}
  {{- with $v.bookstack.extraEnvFrom }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
env:
  - name: APP_KEY
    valueFrom:
      secretKeyRef:
        name: {{ include "bookstack.appKeySecretName" .ctx }}
        key: {{ $v.bookstack.appKey.secretKey }}
  - name: DB_PASSWORD
    valueFrom:
      secretKeyRef:
        name: {{ include "bookstack.db.secretName" .ctx }}
        key: {{ include "bookstack.db.passwordKey" .ctx }}
  {{- if .useS3 }}
  - name: STORAGE_S3_KEY
    valueFrom:
      secretKeyRef:
        name: {{ $v.bookstack.s3.existingSecret }}
        key: {{ $v.bookstack.s3.accessKeyIdKey }}
  - name: STORAGE_S3_SECRET
    valueFrom:
      secretKeyRef:
        name: {{ $v.bookstack.s3.existingSecret }}
        key: {{ $v.bookstack.s3.secretAccessKeyKey }}
  {{- end }}
  {{- with $v.bookstack.extraEnv }}
  {{- toYaml . | nindent 2 }}
  {{- end }}
{{- end }}

{{- define "bookstack.appMounts" -}}
volumeMounts:
  - { name: data, mountPath: /var/www/bookstack/storage, subPath: storage }
  - { name: data, mountPath: /var/www/bookstack/public/uploads, subPath: public-uploads }
  - { name: bootstrap-cache, mountPath: /var/www/bookstack/bootstrap/cache }
  - { name: app-tmp, mountPath: /tmp }
  - { name: php-conf, mountPath: /etc/bookstack/php.d, readOnly: true }
{{- end }}
