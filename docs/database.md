# Database and secrets

BookStack needs MySQL 8.0+ or MariaDB 10.6+. The chart either runs MariaDB
itself or connects to one you provide. Exactly one is used, chosen by
`mariadb.enabled`.

Examples on this page assume release `wiki` in namespace `bookstack`, so
resources are named `wiki-bookstack*`.

## Built-in MariaDB (default)

`mariadb.enabled: true` deploys a single-replica StatefulSet from the official
`mariadb` image, pinned to the `11.8` LTS series.

- The database and user named in `mariadb.auth` are created on first start.
- `MARIADB_AUTO_UPGRADE=1` runs `mariadb-upgrade` after an image change, so
  patch and minor updates within a series apply without manual steps.
- Server settings come from `mariadb.config`, mounted as
  `/etc/mysql/conf.d/zz-chart.cnf`. The default sets utf8mb4, disables reverse
  DNS lookups and uses a 256 MB InnoDB buffer pool. Keep
  `mariadb.resources.limits.memory` comfortably above the buffer pool.
- The data volume comes from a `volumeClaimTemplate` with
  `persistentVolumeClaimRetentionPolicy: Retain`. Deleting or scaling the
  StatefulSet never deletes the data.

The application connects to the headless Service `wiki-bookstack-mariadb`.
You don't need to set `externalDatabase` at all.

## External database

```yaml
mariadb:
  enabled: false
externalDatabase:
  host: mariadb.databases.svc
  port: 3306
  database: bookstack
  username: bookstack
  existingSecret: bookstack-db
  passwordKey: password
```

Create the database and user first, with full privileges on that database.
BookStack manages its own schema through migrations:

```sql
CREATE DATABASE bookstack CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'bookstack'@'%' IDENTIFIED BY '<password>';
GRANT ALL PRIVILEGES ON bookstack.* TO 'bookstack'@'%';
```

and the Secret:

```console
kubectl -n bookstack create secret generic bookstack-db \
  --from-literal=password='<password>'
```

The chart fails to render if `externalDatabase.host` or
`externalDatabase.existingSecret` is empty while `mariadb.enabled` is false.

## Secrets the chart manages

| Secret | Keys | Created when |
|--------|------|--------------|
| `wiki-bookstack-app-key` | `APP_KEY` | `bookstack.appKey.existingSecret` is empty |
| `wiki-bookstack-mariadb` | `mariadb-password`, `mariadb-root-password` | built-in MariaDB, `mariadb.auth.existingSecret` empty |

Values are generated on first install. On every later `helm upgrade` the chart
reads the existing Secret from the cluster and reuses it, so they never change.
Both Secrets carry `helm.sh/resource-policy: keep`; `helm uninstall` leaves
them in place.

> **`helm template` and `--dry-run` without cluster access generate new
> values each time.** That is expected. Only an install or upgrade against
> the cluster reuses the stored ones. Don't apply rendered output from a
> disconnected `helm template` over a running release.

### APP_KEY

`APP_KEY` encrypts data BookStack stores, including multi-factor
authentication secrets and some settings. **If it is lost or changed, MFA
stops working for every user and that data can't be recovered.** Back it up
alongside the database:

```console
kubectl -n bookstack get secret wiki-bookstack-app-key \
  -o jsonpath='{.data.APP_KEY}' | base64 -d; echo
```

To supply your own key, generate one in Laravel's format and reference it:

```console
kubectl -n bookstack create secret generic bookstack-app-key \
  --from-literal=APP_KEY="base64:$(head -c 32 /dev/urandom | base64)"
```

```yaml
bookstack:
  appKey:
    existingSecret: bookstack-app-key
```

## First login

BookStack seeds one administrator on first migration: **`admin@admin.com` /
`password`**. Sign in and change both immediately, or set up the
authentication method you intend to use first (see `AUTH_METHOD` and the OIDC,
SAML or LDAP settings in BookStack's documentation, passed through
`bookstack.env` and `extraEnv`).

## Backup and restore

A complete backup has three parts:

1. the database;
2. the uploads on the PVC, `storage/uploads` (secure images, attachments) and
   `public/uploads` (system images);
3. `APP_KEY` (see above).

Storage-level tools (Velero, CSI snapshots) cover parts 1 and 2 if they
snapshot both PVCs together. The commands below are a tool-free alternative.

### Back up

```console
# 1. Database (built-in MariaDB)
kubectl -n bookstack exec statefulset/wiki-bookstack-mariadb -- \
  sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb-dump -uroot \
         --single-transaction --routines --triggers bookstack' \
  > bookstack-$(date +%F).sql

# 2. Uploads
kubectl -n bookstack exec deploy/wiki-bookstack -c bookstack -- \
  tar -C /var/www/bookstack -czf - storage/uploads public/uploads \
  > bookstack-uploads-$(date +%F).tar.gz

# 3. APP_KEY
kubectl -n bookstack get secret wiki-bookstack-app-key -o yaml \
  > bookstack-app-key-$(date +%F).yaml
```

`--single-transaction` gives a consistent dump without locking BookStack out.
The archives contain everything needed to rebuild the wiki. Store them
encrypted.

### Restore

Into a fresh release of the same chart version:

```console
# APP_KEY first, so the release adopts it instead of generating a new one
kubectl -n bookstack apply -f bookstack-app-key-<date>.yaml

helm install wiki bookstack/bookstack -n bookstack -f my-values.yaml

# Database (after the MariaDB pod is Ready)
kubectl -n bookstack exec -i statefulset/wiki-bookstack-mariadb -- \
  sh -c 'MYSQL_PWD="$MARIADB_ROOT_PASSWORD" mariadb -uroot bookstack' \
  < bookstack-<date>.sql

# Uploads
kubectl -n bookstack exec -i deploy/wiki-bookstack -c bookstack -- \
  tar -C /var/www/bookstack -xzf - < bookstack-uploads-<date>.tar.gz

# Clear caches so BookStack picks up the restored state
kubectl -n bookstack exec deploy/wiki-bookstack -c bookstack -- \
  php artisan cache:clear
```

If the restored database came from an older BookStack version, restart the
pod (`kubectl -n bookstack rollout restart deploy/wiki-bookstack`) so the
`migrate` init container brings the schema up to date.

## Moving between built-in and external

1. Back up the database and uploads as above.
2. Load the dump into the external server and create its Secret.
3. `helm upgrade` with `mariadb.enabled: false` and `externalDatabase` set.
   The uploads PVC and `APP_KEY` are unchanged.
4. Once verified, delete the retained MariaDB PVC (`data-wiki-bookstack-mariadb-0`)
   and Secret, which the chart leaves behind on purpose.
