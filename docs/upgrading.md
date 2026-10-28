# Upgrading and uninstalling

Examples assume release `wiki` in namespace `bookstack`.

## Before any upgrade

1. **Back up** the database, uploads and `APP_KEY`. See
   [Database → Backup and restore](database.md#backup-and-restore).
   BookStack migrations are one-way. Restoring from backup is the only way to
   roll back a version.
2. Read the release notes for every BookStack version you are crossing. Most
   BookStack releases include security fixes, and some change requirements.
3. Preview the change:

```console
   helm diff upgrade wiki bookstack/bookstack -n bookstack -f my-values.yaml   # helm-diff plugin
   # or
   helm template wiki bookstack/bookstack -n bookstack -f my-values.yaml > new.yaml
```

## Upgrading BookStack

Each chart release pins a BookStack version (`appVersion`) and an image built
for it. Upgrading the chart upgrades BookStack:

```console
helm repo update
helm upgrade wiki bookstack/bookstack -n bookstack -f my-values.yaml
```

What happens:

1. The Deployment's `Recreate` strategy stops the old pod. Expect a short
   outage, typically under a minute.
2. The new pod's `wait-for-database` init container confirms the database
   accepts a login, then `migrate` runs `php artisan migrate --force` against
   the existing database.
3. php-fpm and nginx start, and the pod becomes Ready once `/status` passes.

Watch it:

```console
kubectl -n bookstack get pods -w
kubectl -n bookstack logs deploy/wiki-bookstack -c wait-for-database
kubectl -n bookstack logs deploy/wiki-bookstack -c migrate
```

### Pinning or overriding the version

`image.tag` defaults to the chart's `appVersion`. Setting it explicitly pins
BookStack independently of the chart, for example to stay on a version while
taking chart fixes:

```yaml
image:
  tag: v26.09.2
```

For a fully reproducible deployment, set `image.digest` instead. It takes
precedence over the tag.

Only use image tags built from this repository. The chart relies on the
image's layout: non-root user, paths, the `/etc/bookstack/php.d` scan
directory, and php-fpm on loopback.

### If the database wait fails

`wait-for-database` exits non-zero in two cases, and its log says which:

- **Access denied or unknown database.** It fails on the first attempt: the
  password Secret, username or database name does not match the server.
  Waiting would not help.
- **Not ready after the timeout.** The server never accepted a connection:
  check the MariaDB pod (`kubectl -n bookstack get pods`) or, for an external
  database, its host, port and network policy.

### If a migration fails

The `migrate` init container exits non-zero and the pod stays in
`Init:CrashLoopBackOff`. The previous version is already stopped, so the wiki
is down until this is resolved.

1. Read the error: `kubectl -n bookstack logs deploy/wiki-bookstack -c migrate`.
2. If it's transient (database not reachable), the pod recovers by itself
   once the database is back.
3. Otherwise, roll back the release *and* restore the database backup taken
   before the upgrade. `helm rollback` alone restores the old image but not
   the old schema.

## Upgrading MariaDB (built-in)

### Within a series (patch and minor)

`mariadb.image.tag` is a series tag (`11.8`), so new patch releases arrive
whenever the pod is recreated and pulls the image. `MARIADB_AUTO_UPGRADE=1`
runs `mariadb-upgrade` on start. No manual steps are needed.

To control exactly when this happens, pin a full version or a digest:

```yaml
mariadb:
  image:
    tag: "11.8.6"   # example
```

### To a new series

Moving to a newer LTS series is a deliberate change:

1. Back up the database.
2. Set `mariadb.image.tag` to the new series and `helm upgrade`.
3. The StatefulSet restarts MariaDB on the new version and
   `MARIADB_AUTO_UPGRADE` upgrades the system tables. Confirm with
   `kubectl -n bookstack logs statefulset/wiki-bookstack-mariadb`.

MariaDB does not support downgrading a data directory. To go back, restore
the dump into a fresh volume on the old version.

## Changing values

Configuration changes (ConfigMap contents, PHP settings, nginx settings) change
checksum annotations on the pod, so `helm upgrade` rolls it automatically.
Secrets referenced through `existingSecret` are not checksummed. After
rotating one, restart the pod:

```console
kubectl -n bookstack rollout restart deploy/wiki-bookstack
```

Some values must not change on an existing release:

| Value | Why |
|-------|-----|
| `bookstack.appKey.*` (pointing at a different key) | Invalidates MFA and other encrypted data |
| `mariadb.auth.database` / `username` | Only applied when MariaDB initialises an empty volume |
| `mariadb.auth.existingSecret` (different passwords) | MariaDB keeps the passwords it was initialised with; change them in SQL first |
| `persistence.*` / `mariadb.persistence.*` size class or name | PVC specs are mostly immutable; resize only where the StorageClass allows expansion |
| `bookstack.storageType` | Existing files are not moved; see [Storage](storage.md#changing-modes-on-an-existing-wiki) |

## Uninstalling

```console
helm uninstall wiki -n bookstack
```

To protect data, this **leaves behind**:

| Resource | Name | Why it's kept |
|----------|------|---------------|
| Secret | `wiki-bookstack-app-key` | `APP_KEY`, needed to read MFA and encrypted data |
| Secret | `wiki-bookstack-mariadb` | Database passwords matching the data volume |
| PVC | `wiki-bookstack-data` | Uploads and `storage/` |
| PVC | `data-wiki-bookstack-mariadb-0` | The database |

Re-installing with the same release name and namespace picks all of them up
again, so the wiki comes back as it was.

To remove everything permanently:

```console
kubectl -n bookstack delete secret wiki-bookstack-app-key wiki-bookstack-mariadb
kubectl -n bookstack delete pvc wiki-bookstack-data data-wiki-bookstack-mariadb-0
```

Whether deleting a PVC also deletes the underlying storage depends on the
StorageClass's reclaim policy (`Delete` removes it, `Retain` keeps the
PersistentVolume for manual cleanup).
