# syntax=docker/dockerfile:1
#
# BookStack on Debian's php-fpm (trixie ships PHP 8.4), non-root.
# Pairs with an nginx-unprivileged sidecar in the Helm chart; this image serves
# FastCGI on 127.0.0.1:9000 only.

ARG DEBIAN_SUITE=trixie
ARG PHP_VERSION=8.4

# Extensions BookStack requires: curl dom gd iconv mbstring mysqlnd openssl pdo
# pdo_mysql tokenizer xml zip. iconv/openssl/pdo/tokenizer are in php8.4-common;
# opcache is added for performance.
ARG PHP_PACKAGES="cli curl gd mbstring mysql opcache xml zip"

# ---------------------------------------------------------------------------
# build: fetch the BookStack release, install PHP dependencies, trim
#   BOOKSTACK_VERSION has no default: the single source is appVersion in
#   charts/bookstack/Chart.yaml, passed in by `make image` and CI.
# ---------------------------------------------------------------------------
FROM debian:${DEBIAN_SUITE}-slim AS build

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PHP_VERSION
ARG PHP_PACKAGES
ARG BOOKSTACK_VERSION
ARG BOOKSTACK_REPO=https://source.bookstackapp.com/bookstack.git

# The package list is expanded unquoted on purpose: one word per package.
# hadolint ignore=SC2046
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates git unzip \
        $(for p in ${PHP_PACKAGES}; do printf 'php%s-%s ' "${PHP_VERSION}" "$p"; done); \
    rm -rf /var/lib/apt/lists/*

COPY --from=composer:2 /usr/bin/composer /usr/local/bin/composer

RUN set -eux; \
    test -n "${BOOKSTACK_VERSION}" || { echo "BOOKSTACK_VERSION build arg is required (set from Chart.yaml appVersion; use make image)" >&2; exit 1; }; \
    git clone --depth 1 --branch "${BOOKSTACK_VERSION}" "${BOOKSTACK_REPO}" /var/www/bookstack; \
    rm -rf /var/www/bookstack/.git

WORKDIR /var/www/bookstack

# AWS SDK: keep only the S3 client (used by STORAGE_TYPE=s3) via the SDK's
# supported Composer cleanup hook; drops ~70 MB of unused service clients.
RUN set -eux; \
    composer config --json extra.aws/aws-sdk-php '["S3"]'; \
    composer config scripts.pre-autoload-dump 'Aws\Script\Composer\Composer::removeUnusedServices'; \
    composer install --no-dev --optimize-autoloader --no-interaction --no-progress; \
    rm -rf /root/.composer /root/.cache

# Remove build-, test- and dev-only paths. Compiled front-end assets are already
# in public/dist; resources/views, resources/icons and lang/ are runtime files.
RUN set -eux; \
    rm -rf tests dev .forgejo .github resources/js resources/sass \
           package.json package-lock.json phpunit.xml .gitattributes .gitignore; \
    test -f artisan; test -d public/dist; test -d resources/views

# ---------------------------------------------------------------------------
# runtime
# ---------------------------------------------------------------------------
FROM debian:${DEBIAN_SUITE}-slim AS runtime

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG PHP_VERSION
ARG PHP_PACKAGES
ARG BOOKSTACK_VERSION

LABEL org.opencontainers.image.title="bookstack" \
      org.opencontainers.image.description="BookStack on Debian php-fpm, non-root" \
      org.opencontainers.image.source="https://github.com/Jaturu/bookstack-helm" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${BOOKSTACK_VERSION}"

# The package list is expanded unquoted on purpose: one word per package.
# hadolint ignore=SC2046
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates "php${PHP_VERSION}-fpm" \
        $(for p in ${PHP_PACKAGES}; do printf 'php%s-%s ' "${PHP_VERSION}" "$p"; done); \
    rm -rf /var/lib/apt/lists/*; \
    # Debian's default pool (socket, user www-data, pid in /run/php) is replaced
    # by our php-fpm.conf as the single source of fpm settings.
    rm -f "/etc/php/${PHP_VERSION}/fpm/pool.d/www.conf"; \
    ln -s "/usr/sbin/php-fpm${PHP_VERSION}" /usr/local/bin/php-fpm; \
    php -m | grep -qx 'gd'; php -m | grep -qx 'pdo_mysql'; php -m | grep -qx 'zip'; \
    php -m | grep -qx 'Zend OPcache'

COPY php/php-fpm.conf  /etc/php/${PHP_VERSION}/fpm/php-fpm.conf
COPY php/bookstack.ini /etc/php/${PHP_VERSION}/fpm/conf.d/99-bookstack.ini
COPY php/bookstack.ini /etc/php/${PHP_VERSION}/cli/conf.d/99-bookstack.ini

# Extra ini directory scanned after the SAPI defaults (a leading ":" appends to
# the compiled-in conf.d). The Helm chart mounts its generated ini here, so its
# settings override bookstack.ini without depending on the PHP version path.
ENV PHP_INI_SCAN_DIR=":/etc/bookstack/php.d"
RUN mkdir -p /etc/bookstack/php.d

# Application code is root-owned and read-only to the runtime user.
COPY --from=build /var/www/bookstack /var/www/bookstack

# Only the paths BookStack writes to are owned by www-data (uid/gid 33).
#   storage/          – sessions, cache, logs, secure uploads (PVC in the chart)
#   bootstrap/cache/  – Laravel compiled config/services
#   public/uploads/   – system images (app logo), shared with nginx (PVC subPath)
WORKDIR /var/www/bookstack
RUN set -eux; \
    mkdir -p public/uploads; \
    chown -R www-data:www-data storage bootstrap/cache public/uploads; \
    chmod -R u+rwX,go-w storage bootstrap/cache public/uploads

USER 33:33
EXPOSE 9000
CMD ["php-fpm", "--nodaemonize", "--force-stderr"]
