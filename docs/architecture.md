# Architecture

This page explains what the chart deploys and why it is laid out the way it is.
For every configurable value see the
[values reference](../charts/bookstack/README.md#values).

## Components

```
                 Gateway / Ingress  (TLS terminates here)
                          │  HTTP
                          ▼
              Service <release>-bookstack :80
                          │
  ┌───────────────── BookStack pod (Deployment, 1 replica) ─────────────────┐
  │                                                                         │
  │  init: copy-assets ── copies public/ and bootstrap/cache into emptyDirs  │
  │  init: wait-for-database ── until the database accepts a login           │
  │  init: migrate     ── php artisan migrate --force                        │
  │                                                                         │
  │  ┌──────────────── nginx ────────────────┐   ┌──────── bookstack ──────┐ │
  │  │ :8080 app server  (Service → here)    │   │ php-fpm                 │ │
  │  │   static files from public/           │──▶│ 127.0.0.1:9000 only     │ │
  │  │   everything else → index.php         │   │                         │ │
  │  │ :8081 health server (/fpm-ping)       │──▶│                         │ │
  │  └───────────────────────────────────────┘   └─────────────────────────┘ │
  └─────────────────────────────────────────────────────────────────────────┘
                          │  3306
                          ▼
        MariaDB StatefulSet (optional) ── or an external database
```

| Workload | Kind | Image |
|----------|------|-------|
| BookStack | Deployment, `Recreate` strategy | `ghcr.io/jaturu/bookstack` (php-fpm) + `nginxinc/nginx-unprivileged` |
| MariaDB *(optional)* | StatefulSet, 1 replica | `mariadb` (official) |

### Why two containers

The BookStack image contains only the application and php-fpm. nginx runs as a
sidecar from the upstream unprivileged image. Each process has its own
resource limits and liveness probe, so a hung php-fpm restarts only the
`bookstack` container, and nginx can be patched independently of the
application image.

php-fpm listens on `127.0.0.1:9000`, so FastCGI is reachable only from
inside the pod. The only port the Service exposes is nginx's `http`
port.

## Startup sequence

1. **`copy-assets`** copies `public/` (compiled CSS/JS, icons) and the Laravel
   `bootstrap/cache` from the image into `emptyDir` volumes, and seeds the
   `storage/` directory structure onto the PVC without overwriting anything
   already there. nginx serves `public/` from its own container;
   `bootstrap/cache` and `storage/` must be writable while the root filesystem
   is read-only.
2. **`wait-for-database`** retries a database login every two seconds until
   it succeeds. On a first install the built-in MariaDB spends a minute or so
   initialising; without the wait, `migrate` would fail and restart with
   backoff until it was ready. Errors that waiting cannot fix (bad
   credentials, a missing database) fail at once with a clear message, and
   the wait gives up after `migrations.waitForDatabase.timeoutSeconds`
   (default 300). The script is
   [`charts/bookstack/files/wait-for-database.php`](../charts/bookstack/files/wait-for-database.php),
   run with the image's own PHP.
3. **`migrate`** runs `php artisan migrate --force`.
4. **`bookstack`** (php-fpm) and **`nginx`** start.

`wait-for-database`, `migrate` and `bookstack` get their environment from the
same helper, so they always use the same database settings; `migrate` and
`bookstack` also share identical mounts.

## Request handling

nginx's application server:

- serves files that exist under `public/` directly; `/dist/` (compiled assets)
  is cached for 7 days;
- passes every other request to `index.php`. Uploads that BookStack serves
  itself, such as the image URLs under `local_secure_restricted`, therefore
  always reach PHP and its permission checks;
- refuses to execute any other `.php` path, and denies dotfiles.

`X-Forwarded-Proto` / `X-Forwarded-For` from the gateway reach PHP unchanged;
BookStack honours them for the proxies listed in `bookstack.trustedProxies`.

## Volumes

| Volume | Backing | Mounted in | Path | Mode |
|--------|---------|------------|------|------|
| `data` → subPath `storage` | PVC | bookstack, migrate | `/var/www/bookstack/storage` | rw |
| `data` → subPath `storage` | PVC | copy-assets | `/storage` | rw (seeding only) |
| `data` → subPath `public-uploads` | PVC | bookstack, migrate | `/var/www/bookstack/public/uploads` | rw |
| `data` → subPath `public-uploads` | PVC | nginx | `/var/www/bookstack/public/uploads` | ro |
| `public` | emptyDir | nginx | `/var/www/bookstack/public` | ro |
| `bootstrap-cache` | emptyDir | bookstack, migrate | `/var/www/bookstack/bootstrap/cache` | rw |
| `app-tmp` / `nginx-tmp` | emptyDir | each container | `/tmp` | rw |
| `nginx-conf` | ConfigMap | nginx | `/etc/nginx/conf.d` | ro |

A single PVC holds both subPaths:

- **`storage/`**: secure image uploads, attachments, sessions, cache and
  logs. Only php-fpm mounts it.
- **`public-uploads/`**: *system* images such as the application logo, which
  BookStack always stores publicly even in the secure storage modes. nginx
  mounts it read-only to serve them.

Both containers are in one pod, so `ReadWriteOnce` is sufficient. That is
also why the Deployment is fixed at one replica with the `Recreate` strategy:
the old pod must release the volume before the new one mounts it. The chart
refuses `replicaCount` values other than 1.

## Security model

Every container, including init containers and MariaDB, runs with:

- `runAsNonRoot: true`: the BookStack pod (php-fpm, nginx and init
  containers) as uid/gid 33 (`www-data`), MariaDB as 999 (`mysql`);
- `readOnlyRootFilesystem: true`, with writable paths limited to the volumes
  listed above;
- `allowPrivilegeEscalation: false`, all capabilities dropped,
  `seccompProfile: RuntimeDefault`.

This satisfies the `restricted` Pod Security Standard, so the release
namespace can be labelled
`pod-security.kubernetes.io/enforce: restricted`.

Pods also disable service-account token mounting and service-link
environment variables; BookStack needs neither.

Inside the image, the application code is owned by root and read-only to
`www-data`. Only `storage/`, `bootstrap/cache/` and `public/uploads/` are
writable, and in the pod those are volumes anyway.

## Health checks

| Container | Probe | Check |
|-----------|-------|-------|
| bookstack | liveness | `GET :8081/fpm-ping`, through nginx's health server to php-fpm |
| nginx | liveness | TCP connect to `:8080` |
| nginx | readiness | `GET :8080/status`, BookStack's own check of the database, cache and session store |
| mariadb | startup / liveness / readiness | `healthcheck.sh` from the official image |

The health server on port 8081 is not part of the Service, so `/fpm-ping` is
reachable only by the kubelet. php-fpm's `/fpm-status` page is not routed
anywhere.

Because readiness uses `/status`, a pod that loses its database connection
drops out of the Service endpoints instead of serving errors.

## Configuration flow

| Source | Becomes | Used by |
|--------|---------|---------|
| Modelled values (`bookstack.appUrl`, storage, DB connection, ...) | ConfigMap `<release>-bookstack` | `envFrom` |
| `bookstack.env` | same ConfigMap | `envFrom` |
| APP_KEY, DB password, S3 keys | Secrets | `secretKeyRef` |
| `bookstack.extraEnv` / `extraEnvFrom` | passed through | container env |

Each setting has exactly one source. The chart fails to render if
`bookstack.env` repeats a modelled key or tries to carry a secret. Pods carry
checksums of both ConfigMaps, so a configuration change rolls the pod.
