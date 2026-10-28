# bookstack

![Version: 0.1.3](https://img.shields.io/badge/Version-0.1.3-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: v26.09.2](https://img.shields.io/badge/AppVersion-v26.09.2-informational?style=flat-square)

BookStack wiki on a non-root php-fpm image with an nginx-unprivileged sidecar, optional built-in MariaDB (official image), and Gateway API HTTPRoute support.

[BookStack](https://www.bookstackapp.com/) is a self-hosted wiki for organising
documentation into shelves, books, chapters and pages. This chart runs it on a
purpose-built, non-root image and is designed to pass the Kubernetes
`restricted` Pod Security Standard.

## Features

- **Non-root php-fpm + nginx-unprivileged** in one pod, read-only root
  filesystems, all capabilities dropped, `RuntimeDefault` seccomp.
- **Optional built-in MariaDB** (official `mariadb` image, LTS series) or any
  external MySQL 8.0+ / MariaDB 10.6+.
- **Generated secrets that survive upgrades** — `APP_KEY` and database
  passwords are created on first install, reused on every upgrade and kept on
  uninstall.
- **Permission-checked uploads by default** (`local_secure_restricted`), with
  `local`, `local_secure` and S3-compatible storage also supported.
- **Gateway API `HTTPRoute`** and/or **`Ingress`**.
- **Automatic migrations** in an init container before BookStack starts.
- **Render-time validation** of required and conflicting values.

## Installing

```console
helm repo add bookstack https://jaturu.github.io/bookstack-helm
helm repo update
helm install wiki bookstack/bookstack \
  --namespace bookstack --create-namespace \
  --set bookstack.appUrl=https://wiki.example.com
```

Or install straight from the OCI registry, without `helm repo add`:

```console
helm install wiki oci://ghcr.io/jaturu/charts/bookstack --version 0.1.3 \
  --namespace bookstack --create-namespace \
  --set bookstack.appUrl=https://wiki.example.com
```

`bookstack.appUrl` is the only required value. The first login is
`admin@admin.com` / `password` — change it immediately.

### Example: Gateway API

```yaml
bookstack:
  appUrl: https://wiki.example.com
  # Pod network of the gateway, so BookStack trusts X-Forwarded-* headers.
  trustedProxies: "10.244.0.0/16"

httpRoute:
  enabled: true
  parentRefs:
    - name: my-gateway
      namespace: gateway-system
      sectionName: https
  hostnames:
    - wiki.example.com

persistence:
  storageClass: fast-rwo
mariadb:
  persistence:
    storageClass: fast-rwo
```

### Example: Ingress with cert-manager

```yaml
bookstack:
  appUrl: https://wiki.example.com
  trustedProxies: "10.0.0.0/8"

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
    nginx.ingress.kubernetes.io/proxy-body-size: 55m
  hosts:
    - wiki.example.com
  tls:
    - secretName: wiki-tls
      hosts:
        - wiki.example.com
```

## Guides

| Guide | Covers |
|-------|--------|
| [Installing](https://github.com/Jaturu/bookstack-helm/blob/main/docs/installing.md) | A production install behind a gateway, from namespace to first login |
| [Architecture](https://github.com/Jaturu/bookstack-helm/blob/main/docs/architecture.md) | Pod layout, volumes, security model, probes |
| [Storage](https://github.com/Jaturu/bookstack-helm/blob/main/docs/storage.md) | Upload storage modes and their permission behaviour, S3 / ObjectBucketClaim |
| [Database](https://github.com/Jaturu/bookstack-helm/blob/main/docs/database.md) | Built-in vs external database, secrets, backup and restore |
| [Exposure](https://github.com/Jaturu/bookstack-helm/blob/main/docs/exposure.md) | HTTPRoute and Ingress, TLS, trusted proxies, upload size limits |
| [Email](https://github.com/Jaturu/bookstack-helm/blob/main/docs/email.md) | SMTP settings, the password Secret, testing |
| [Upgrading](https://github.com/Jaturu/bookstack-helm/blob/main/docs/upgrading.md) | BookStack and MariaDB upgrades, what uninstall leaves behind |
| [Image](https://github.com/Jaturu/bookstack-helm/blob/main/docs/image.md) | How the container image is built and versioned |

## Uninstalling

```console
helm uninstall wiki -n bookstack
```

By design this **keeps** the `APP_KEY` and MariaDB Secrets, the uploads PVC and
the MariaDB data PVC. Delete them explicitly to remove all data — see
[Upgrading](https://github.com/Jaturu/bookstack-helm/blob/main/docs/upgrading.md#uninstalling).

## Requirements

Kubernetes: `>=1.29.0-0`

## Values

| Key | Type | Default | Description |
|-----|------|---------|-------------|
| affinity | object | `{}` | Affinity rules for the BookStack pod. |
| bookstack.appKey.existingSecret | string | `""` | Use an existing Secret instead of the chart-managed one. |
| bookstack.appKey.secretKey | string | `"APP_KEY"` | Key inside the Secret holding the value (format: base64:<32 bytes>). |
| bookstack.appUrl | string | `""` | Public base URL, including scheme, no trailing slash. REQUIRED. BookStack uses this for every generated link and redirect. Example: https://wiki.example.com |
| bookstack.env | object | `{}` | Additional BookStack .env settings as plain key/value pairs, rendered into a ConfigMap. Use for anything not modelled above (MAIL_*, AUTH_METHOD, OIDC_*, ...). Secret values belong in extraEnvFrom / extraEnv instead. See https://github.com/BookStackApp/BookStack/blob/release/.env.example.complete |
| bookstack.extraEnv | list | `[]` | Extra container env entries (full EnvVar objects, e.g. secretKeyRef). |
| bookstack.extraEnvFrom | list | `[]` | Extra envFrom sources (whole Secrets/ConfigMaps). |
| bookstack.lang | string | `"en"` | Default UI language (APP_LANG). |
| bookstack.s3.accessKeyIdKey | string | `"AWS_ACCESS_KEY_ID"` | Key in s3.existingSecret holding the access key ID. |
| bookstack.s3.bucket | string | `""` | Bucket name (STORAGE_S3_BUCKET). Required when S3 storage is used. |
| bookstack.s3.endpoint | string | `""` | Custom endpoint URL for non-AWS S3 (e.g. http://rook-ceph-rgw.rook-ceph.svc). |
| bookstack.s3.existingSecret | string | `""` | Secret holding the access key pair. Key names default to the ones a Rook/Ceph ObjectBucketClaim Secret uses, so an OBC Secret works directly. |
| bookstack.s3.region | string | `"us-east-1"` | Bucket region (STORAGE_S3_REGION). Any value works for Ceph RGW / MinIO. |
| bookstack.s3.secretAccessKeyKey | string | `"AWS_SECRET_ACCESS_KEY"` | Key in s3.existingSecret holding the secret access key. |
| bookstack.s3.url | string | `""` | Public base URL images are fetched from (STORAGE_URL). Must be reachable by users' browsers. Empty = derived by BookStack. |
| bookstack.storageAttachmentType | string | `""` | Override storage for attachments only (STORAGE_ATTACHMENT_TYPE). Empty = storageType. |
| bookstack.storageImageType | string | `""` | Optional per-type overrides (STORAGE_IMAGE_TYPE / STORAGE_ATTACHMENT_TYPE). Empty = use storageType. |
| bookstack.storageType | string | `"local_secure_restricted"` | Upload storage mode for images and attachments.   local_secure_restricted – served via BookStack with per-item permission                              checks (default)   local_secure            – served via BookStack, login required only   local                   – images public under /uploads   s3                      – S3-compatible bucket (images public by URL);                              configure under bookstack.s3 |
| bookstack.timezone | string | `"UTC"` | Application timezone (APP_TIMEZONE). |
| bookstack.trustedProxies | string | `""` | Reverse proxies whose X-Forwarded-* headers are trusted (APP_PROXIES). Comma-separated CIDRs, or "*" to trust any. Set this to the gateway/ingress pod network so BookStack sees the real scheme and client IP. |
| bookstack.uploadLimitMB | int | `50` | Upload size limit in MB. Single source for every limit inside the pod: BookStack's FILE_UPLOAD_SIZE_LIMIT, PHP upload_max_filesize (N M) and post_max_size (N+5 M), and nginx client_max_body_size (N+5 m). The Gateway / Ingress in front of the pod must allow at least N+5 MB too. |
| externalDatabase.database | string | `"bookstack"` | Database name. |
| externalDatabase.existingSecret | string | `""` | Secret holding the user's password. REQUIRED when mariadb.enabled=false. |
| externalDatabase.host | string | `""` | Database hostname. Required when mariadb.enabled=false. |
| externalDatabase.passwordKey | string | `"password"` | Key in externalDatabase.existingSecret holding the password. |
| externalDatabase.port | int | `3306` | Database port. |
| externalDatabase.username | string | `"bookstack"` | Database user. |
| fullnameOverride | string | `""` | Override the full resource name prefix (default: <release>-<chart>). |
| httpRoute.annotations | object | `{}` | HTTPRoute annotations. |
| httpRoute.enabled | bool | `false` | Create a Gateway API HTTPRoute. |
| httpRoute.hostnames | list | `[]` | Hostnames, e.g. [wiki.example.com]. Usually matches appUrl. |
| httpRoute.parentRefs | list | `[]` | Gateways to attach to, e.g.   - name: my-gateway     namespace: gateway-system     sectionName: https |
| image.digest | string | `""` | Optional image digest (sha256:...). When set, takes precedence over tag. |
| image.pullPolicy | string | `"IfNotPresent"` | Image pull policy. |
| image.repository | string | `"ghcr.io/jaturu/bookstack"` | Image repository. |
| image.tag | string | `""` | Defaults to the chart's appVersion when empty. |
| imagePullSecrets | list | `[]` | Pull secrets applied to every pod in the release. |
| ingress.annotations | object | `{}` | Controller-specific annotations. Most controllers cap request bodies below the 50 MB upload limit by default – raise theirs too, e.g.   nginx.ingress.kubernetes.io/proxy-body-size: 55m   cert-manager.io/cluster-issuer: my-issuer |
| ingress.className | string | `""` | IngressClass to use. Empty = cluster default class. |
| ingress.enabled | bool | `false` | Create an Ingress. |
| ingress.hosts | list | `[]` | Hostnames, e.g. [wiki.example.com]. Usually matches appUrl. |
| ingress.path | string | `"/"` | Path matched on every host. |
| ingress.pathType | string | `"Prefix"` | Ingress pathType. |
| ingress.tls | list | `[]` | TLS blocks, e.g.   - secretName: wiki-tls     hosts: [wiki.example.com] |
| mariadb.affinity | object | `{}` | Affinity rules for the MariaDB pod. |
| mariadb.auth.database | string | `"bookstack"` | Database created on first start (MARIADB_DATABASE). |
| mariadb.auth.existingSecret | string | `""` | Use an existing Secret for the passwords instead of the chart-managed one (generated on first install, reused on upgrades, kept on uninstall). |
| mariadb.auth.passwordKey | string | `"mariadb-password"` | Key in the MariaDB Secret holding the BookStack user's password. |
| mariadb.auth.rootPasswordKey | string | `"mariadb-root-password"` | Key in the MariaDB Secret holding the root password. |
| mariadb.auth.username | string | `"bookstack"` | User created on first start (MARIADB_USER). |
| mariadb.config | string | `"[mysqld]\ncharacter-set-server  = utf8mb4\ncollation-server      = utf8mb4_unicode_ci\nskip-name-resolve\ninnodb_buffer_pool_size = 256M\n"` | Extra server settings, rendered into a ConfigMap mounted at /etc/mysql/conf.d/zz-chart.cnf. |
| mariadb.enabled | bool | `true` | Deploy MariaDB with the chart. Set false to use externalDatabase. |
| mariadb.image.digest | string | `""` | Optional MariaDB image digest (sha256:...). Takes precedence over tag. |
| mariadb.image.pullPolicy | string | `"IfNotPresent"` | MariaDB image pull policy. |
| mariadb.image.repository | string | `"docker.io/library/mariadb"` | MariaDB image repository (official image). |
| mariadb.image.tag | string | `"11.8"` | 11.8 is the current MariaDB LTS series; the tag follows its patches. |
| mariadb.nodeSelector | object | `{}` | Node selector for the MariaDB pod. |
| mariadb.persistence.accessModes | list | `["ReadWriteOnce"]` | Access modes for the data volume. |
| mariadb.persistence.size | string | `"8Gi"` | Size of the data volume. |
| mariadb.persistence.storageClass | string | `""` | StorageClass for the data volume. Empty = cluster default. |
| mariadb.podSecurityContext | object | `{"fsGroup":999,"runAsGroup":999,"runAsNonRoot":true,"runAsUser":999,"seccompProfile":{"type":"RuntimeDefault"}}` | MariaDB pod security context. uid/gid 999 is the mysql user in the official image. |
| mariadb.resources | object | `{"limits":{"memory":"768Mi"},"requests":{"cpu":"50m","memory":"384Mi"}}` | MariaDB container resources. Raise the memory limit with innodb_buffer_pool_size. |
| mariadb.securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}` | MariaDB container security context. /var/lib/mysql, /run/mysqld and /tmp are the only writable paths. |
| mariadb.tolerations | list | `[]` | Tolerations for the MariaDB pod. |
| migrations.enabled | bool | `true` | Run database migrations in an init container before BookStack starts. |
| migrations.waitForDatabase.enabled | bool | `true` | Wait in an init container until the database accepts a login before migrating. Avoids failed migrate attempts while MariaDB initialises. |
| migrations.waitForDatabase.timeoutSeconds | int | `300` | How long to wait, in seconds, before failing the pod start. |
| nameOverride | string | `""` | Override the chart name used in resource names. |
| nginx.image.digest | string | `""` | Optional nginx image digest (sha256:...). Takes precedence over tag. |
| nginx.image.pullPolicy | string | `"IfNotPresent"` | nginx image pull policy. |
| nginx.image.repository | string | `"docker.io/nginxinc/nginx-unprivileged"` | nginx sidecar image repository. |
| nginx.image.tag | string | `"1.30-alpine"` | nginx sidecar image tag (1.30 = current stable branch). |
| nginx.port | int | `8080` | Container port nginx listens on (unprivileged, >1024). |
| nodeSelector | object | `{}` | Node selector for the BookStack pod. |
| persistence.accessModes | list | `["ReadWriteOnce"]` | Access modes for the data volume. |
| persistence.annotations | object | `{}` | Extra annotations on the PVC (helm.sh/resource-policy: keep is always set). |
| persistence.enabled | bool | `true` | Persist uploads and storage/. When false an emptyDir is used (data lost on pod restart). |
| persistence.existingClaim | string | `""` | Use an existing PVC instead of creating one. |
| persistence.size | string | `"10Gi"` | Size of the data volume. |
| persistence.storageClass | string | `""` | StorageClass for the data volume. Empty = cluster default. |
| php.extraIni | string | `""` | Extra PHP ini settings, appended after the derived upload limits. Do not set upload_max_filesize or post_max_size here; use bookstack.uploadLimitMB. Example:   memory_limit = 512M   max_execution_time = 300 |
| podAnnotations | object | `{}` | Extra annotations on the BookStack pod. |
| podLabels | object | `{}` | Extra labels on the BookStack pod. |
| podSecurityContext | object | `{"fsGroup":33,"fsGroupChangePolicy":"OnRootMismatch","runAsGroup":33,"runAsNonRoot":true,"runAsUser":33,"seccompProfile":{"type":"RuntimeDefault"}}` | Pod-level security context. uid/gid 33 is www-data in the BookStack image. |
| probes.healthPort | int | `8081` | Port of nginx's health server (/fpm-ping). Not exposed by the Service. |
| probes.liveness | object | `{"failureThreshold":3,"initialDelaySeconds":10,"periodSeconds":20,"timeoutSeconds":3}` | Liveness probe timings (php-fpm via /fpm-ping; nginx via TCP). |
| probes.readiness | object | `{"failureThreshold":3,"initialDelaySeconds":5,"periodSeconds":10,"timeoutSeconds":5}` | Readiness probe timings (BookStack /status: database, cache, session). |
| replicaCount | int | `1` | Fixed at 1: the data volume is ReadWriteOnce and the Deployment uses the Recreate strategy so the old pod releases it before the new one starts. |
| resources.app | object | `{"limits":{"memory":"512Mi"},"requests":{"cpu":"50m","memory":"192Mi"}}` | php-fpm container resources (also used by the init containers). |
| resources.nginx | object | `{"limits":{"memory":"128Mi"},"requests":{"cpu":"10m","memory":"32Mi"}}` | nginx sidecar resources. |
| securityContext | object | `{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]},"readOnlyRootFilesystem":true}` | Container security context (applied to php-fpm, nginx and init containers). The root filesystem is read-only; the chart mounts emptyDirs for /tmp and bootstrap/cache. |
| service.annotations | object | `{}` | Service annotations. |
| service.port | int | `80` | Service port (targets nginx's http port). |
| service.type | string | `"ClusterIP"` | Service type. |
| tests.enabled | bool | `true` | Render the `helm test` pod (templates/test-connection.yaml). |
| tolerations | list | `[]` | Tolerations for the BookStack pod. |

----------------------------------------------
Autogenerated from chart metadata using [helm-docs v1.14.2](https://github.com/norwoodj/helm-docs/releases/v1.14.2)
