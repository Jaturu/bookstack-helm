# The container image

`ghcr.io/jaturu/bookstack` is built from [`image/`](../image) in this
repository specifically for this chart. It contains BookStack and php-fpm, and
nothing else. The nginx sidecar uses the upstream `nginxinc/nginx-unprivileged`
image.

## Contents

| Item | Value |
|------|-------|
| Base | `debian:trixie-slim` |
| PHP | Debian's `php8.4-fpm` and `php8.4-cli`, with `curl gd mbstring mysql opcache xml zip` |
| BookStack | The release tag named by `appVersion` in `charts/bookstack/Chart.yaml` |
| Runs as | uid/gid 33 (`www-data`) |
| Listens | php-fpm FastCGI on `127.0.0.1:9000` only |
| App path | `/var/www/bookstack` |
| Command | `php-fpm --nodaemonize --force-stderr` |

The image ships no web server and no compiler toolchain. Git and Composer
are used only in the build stage and are not in the final image.

## Version: one source

The BookStack version is set **only** in `charts/bookstack/Chart.yaml`:

```yaml
appVersion: "v26.09.2"
```

- The Dockerfile's `BOOKSTACK_VERSION` build arg has no default. A build
  without it fails immediately.
- `make image` and CI read `appVersion` and pass it as the build arg and the
  image tag.
- The chart's `image.tag` defaults to `appVersion`.

So the chart's default image is always the image built from the same
BookStack release.

## How it is built

The [Dockerfile](../image/Dockerfile) has two stages.

**build**

1. Installs the same PHP packages as the runtime, plus git and unzip, so
   Composer resolves dependencies against exactly the extensions the image
   will have.
2. Clones the release tag from `source.bookstackapp.com` (shallow, `.git`
   removed).
3. Runs `composer install --no-dev --optimize-autoloader`, with the AWS SDK's
   supported cleanup hook set to keep only the S3 client. That removes about
   70 MB of unused service clients while `STORAGE_TYPE=s3` keeps working.
4. Removes paths not needed at runtime: `tests/`, `dev/`, `.forgejo/`,
   `.github/`, `resources/js`, `resources/sass`, `package*.json`,
   `phpunit.xml`. Compiled front-end assets are already in `public/dist`.
   Views, icons and translations are kept.

**runtime**

1. Installs `php8.4-fpm` and the extension packages, removes Debian's default
   fpm pool, and verifies the required extensions load.
2. Installs the image's PHP configuration (below).
3. Copies the application in, **owned by root**. Only `storage/`,
   `bootstrap/cache/` and `public/uploads/` are made writable by `www-data`.
4. Switches to uid 33.

## PHP configuration and load order

| Order | File | Set by |
|-------|------|--------|
| 1 | `/etc/php/8.4/{fpm,cli}/php.ini` | Debian defaults |
| 2 | `/etc/php/8.4/{fpm,cli}/conf.d/99-bookstack.ini` | Image: upload limits (50M), memory, opcache, `expose_php = Off` |
| 3 | `/etc/bookstack/php.d/*.ini` | **Chart**: upload limits from `bookstack.uploadLimitMB`, plus `php.extraIni` |

`PHP_INI_SCAN_DIR=":/etc/bookstack/php.d"` appends directory 3 to each SAPI's
built-in scan path. Later files win, so the chart's values override the
image's without depending on the PHP version in the path.

php-fpm uses a single, complete config,
[`image/php/php-fpm.conf`](../image/php/php-fpm.conf): one pool, loopback
listener, no `user` / `group` directives (it runs as the container user), no
pid file, logs to stderr, and `ping` / `status` endpoints for the chart's
probes.

opcache runs with `validate_timestamps = 0`. The code never changes inside a
running container, so PHP doesn't stat files on each request. A new image
means a new pod and a fresh cache.

## Building locally

```console
make version        # prints the BookStack version from Chart.yaml
make image          # builds bookstack:dev and ghcr.io/jaturu/bookstack:<version>
make test-image     # build + contract tests (see Testing)
```

Other build args, rarely changed:

| Arg | Default | Purpose |
|-----|---------|---------|
| `DEBIAN_SUITE` | `trixie` | Debian release for both stages |
| `PHP_VERSION` | `8.4` | Must be the PHP version that suite ships |
| `PHP_PACKAGES` | `cli curl gd mbstring mysql opcache xml zip` | Extension packages, without the `phpX.Y-` prefix |
| `BOOKSTACK_REPO` | `https://source.bookstackapp.com/bookstack.git` | Source repository |

## Releasing a new BookStack version

1. Read the BookStack release notes, especially for changed requirements (PHP
   version, extensions).
2. Edit `appVersion` in `charts/bookstack/Chart.yaml` and bump the chart
   `version`.
3. If requirements changed, adjust `PHP_VERSION`, `DEBIAN_SUITE` or
   `PHP_PACKAGES` in the Dockerfile.
4. `make test-all`: unit, schema, image and install tests (see
   [Testing](testing.md)).
5. Commit. CI builds and publishes the image and the chart.

## Publishing and verification

Releases are built per architecture on native runners, gated by Grype and
Trivy scans, signed keyless with cosign, and published with SBOMs, scan reports
and provenance. Tags, verification commands and the reasoning behind the
pipeline are in [Supply chain](supply-chain.md); whether the current release
has open findings is on the [security status](security-status.md) page.

## Using your own image

`image.repository` / `image.tag` can point at another image only if it keeps
this image's contract:

- application at `/var/www/bookstack`, with `public/` and `bootstrap/cache/`
  readable for the init container to copy;
- php-fpm in the foreground on `127.0.0.1:9000`, with `ping.path = /fpm-ping`;
- runs as a non-root uid that can write `storage/`, `bootstrap/cache/` and
  `public/uploads/` (adjust `podSecurityContext` if it isn't 33);
- PHP scans `/etc/bookstack/php.d` after its own configuration;
- `php artisan` available for the migrate init container.
