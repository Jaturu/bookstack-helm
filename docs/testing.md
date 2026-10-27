# Testing

Four layers, from fastest to most complete. Each catches a different class of
mistake.

| Layer | Command | Needs | Checks |
|-------|---------|-------|--------|
| Template unit tests | `make test-unit` | helm, helm-unittest plugin | Rendering logic: validation guards, derived limits, DB wiring, mounts, env, probes, security contexts, routes |
| Schema validation | `make test-schema` | helm, kubeconform | Rendered manifests are valid Kubernetes / Gateway API objects, across several values scenarios |
| Image contract | `make test-image` | docker | The image provides what the chart relies on |
| Install test | `make test-install` | docker, kind, kubectl, helm | A real install works end to end on a throwaway cluster |

`make test` runs lint + unit + schema (seconds, no cluster). `make test-all`
runs everything.

## Tool setup

```console
# helm-unittest (Helm 4 requires --verify=false for unsigned plugins)
helm plugin install https://github.com/helm-unittest/helm-unittest --version v1.0.3 --verify=false
# Helm 3:
helm plugin install https://github.com/helm-unittest/helm-unittest --version v1.0.3

brew install kubeconform kind     # or download from their GitHub releases
```

## Template unit tests

Suites live in [`charts/bookstack/tests/`](../charts/bookstack/tests) and are
excluded from the packaged chart by `.helmignore`.

| Suite | Covers |
|-------|--------|
| `validation_test.yaml` | Every render-time guard fails with its message; valid input renders |
| `deployment_test.yaml` | Images and digests, init container order, storage seeding, mounts, env, ports, probes, security contexts |
| `configmaps_test.yaml` | App env (built-in vs external DB, S3, `bookstack.env`), derived PHP and nginx limits, nginx hardening |
| `secrets_test.yaml` | Generated secrets, APP_KEY format, **reuse of existing values on upgrade** (simulated cluster), existingSecret handling |
| `mariadb_test.yaml` | StatefulSet, Service, config, retention, security |
| `networking_test.yaml` | Service, PVC, HTTPRoute, Ingress |
| `test-connection_test.yaml` | The `helm test` hook pod |

Run one suite with `helm unittest -f 'tests/secrets_test.yaml' charts/bookstack`.

When you change a template, add or update the test that covers it. When you
fix a bug, add a test that fails without the fix.

## Schema validation

[`tests/schema.sh`](../tests/schema.sh) renders the chart once per file in
[`tests/values/`](../tests/values) and validates the output with
`kubeconform -strict`, using the Kubernetes schemas plus the Gateway API CRD
schemas.

| Scenario | Exercises |
|----------|-----------|
| `default.yaml` | Minimal install |
| `full.yaml` | HTTPRoute + Ingress, S3 attachments, extra env, PHP ini, scheduling |
| `external-db.yaml` | External database, existing Secrets and PVC, migrations off |
| `s3-ephemeral.yaml` | All uploads on S3, no persistence |

Add a scenario file when you add a feature that changes which objects render.
`KUBE_VERSION=1.33.0 tests/schema.sh` pins the schema version.

## Image contract

[`tests/image-test.sh`](../tests/image-test.sh) runs the image the way the
chart does (non-root, read-only root filesystem) and checks: uid/gid 33, the
BookStack version matches `appVersion`, required PHP extensions, php-fpm config
(loopback listener, ping endpoint), Laravel boots, `/etc/bookstack/php.d`
overrides PHP settings for CLI and fpm, ownership of writable vs read-only
paths, the `storage/` skeleton the chart seeds, the trims (build-only paths,
AWS SDK), and that no build tools remain.

## Install test

[`tests/install.sh`](../tests/install.sh) uses a temporary kubeconfig, so it
never touches your current kubectl context. It:

1. builds the image and loads it into a kind cluster (`bookstack-test`);
2. installs into a namespace that **enforces the `restricted` Pod Security
   Standard**, so any security-context regression fails the install;
3. runs `helm test`, the hook pod in
   [`templates/test-connection.yaml`](../charts/bookstack/templates/test-connection.yaml),
   which checks `/status` (database, cache, session), the login page, static
   assets from nginx, and the hardening rules (other `.php` paths 404,
   dotfiles denied);
4. upgrades with a config change and checks that `APP_KEY` and the database
   password are unchanged and the pod rolled;
5. runs `helm test` again;
6. uninstalls and checks the Secrets and PVCs were kept.

On failure it prints pod status, events and logs for every container.
`KEEP_CLUSTER=1` keeps the cluster for inspection; `SKIP_BUILD=1` reuses an
existing image.

`helm test` also works against any real release:

```console
helm test wiki -n bookstack --logs
```

## CI

`ct.yaml` and `charts/bookstack/ci/default-values.yaml` configure
[chart-testing](https://github.com/helm/chart-testing) for the CI pipeline,
which runs the same layers on every pull request.
