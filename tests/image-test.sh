#!/usr/bin/env bash
# Contract tests for the BookStack image: the things the chart relies on.
# Needs: docker, and the image built (make image).
#
#   tests/image-test.sh                     # tests bookstack:dev
#   IMAGE=ghcr.io/jaturu/bookstack:v26.09.2 tests/image-test.sh
set -uo pipefail

cd "$(dirname "$0")/.."
IMAGE=${IMAGE:-bookstack:dev}
VERSION=$(make -s version)
failed=0

# Run like the chart does: non-root, read-only root filesystem, writable /tmp.
run() { docker run --rm --read-only --tmpfs /tmp --entrypoint sh "$@"; }
check() {
  local name=$1; shift
  if out=$("$@" 2>&1); then echo "PASS $name"
  else echo "FAIL $name"; echo "$out" | sed 's/^/    /'; failed=1; fi
}

echo "Testing $IMAGE (expect BookStack $VERSION)"

check "runs as uid/gid 33" \
  run "$IMAGE" -c '[ "$(id -u):$(id -g)" = "33:33" ]'
check "contains BookStack $VERSION" \
  run "$IMAGE" -c "[ \"\$(cat version)\" = '$VERSION' ]"
check "has the PHP extensions BookStack requires" \
  run "$IMAGE" -c 'm=$(php -m); for e in curl dom gd iconv mbstring mysqlnd openssl pdo pdo_mysql tokenizer xml zip "Zend OPcache"; do echo "$m" | grep -qix "$e" || { echo "missing $e"; exit 1; }; done'
check "php-fpm config is valid" \
  run "$IMAGE" -c 'php-fpm -t'
check "php-fpm listens on loopback only, with the ping endpoint" \
  run "$IMAGE" -c 'c=$(php-fpm -tt 2>&1); echo "$c" | grep -q "listen = 127.0.0.1:9000" && echo "$c" | grep -q "ping.path = /fpm-ping"'
check "Laravel boots (php artisan)" \
  run "$IMAGE" -c 'php artisan --version | grep -q "Laravel Framework"'
check "ini files in /etc/bookstack/php.d override the image (cli + fpm)" \
  bash -c "printf 'upload_max_filesize = 77M\n' > /tmp/zz-imgtest.ini && \
    docker run --rm --read-only --tmpfs /tmp -v /tmp/zz-imgtest.ini:/etc/bookstack/php.d/zz.ini:ro --entrypoint sh '$IMAGE' -c \
    '[ \"\$(php -r \"echo ini_get(\\\"upload_max_filesize\\\");\")\" = 77M ] && php-fpm -i | grep -q \"^upload_max_filesize => 77M\"'"
check "writable paths are owned by www-data" \
  run "$IMAGE" -c 'for d in storage bootstrap/cache public/uploads; do [ "$(stat -c %u:%g $d)" = "33:33" ] || { echo "$d"; exit 1; }; done'
check "application code is not writable by the runtime user" \
  run "$IMAGE" -c 'for p in artisan app vendor public/index.php; do [ ! -w "$p" ] || { echo "$p writable"; exit 1; }; [ "$(stat -c %u $p)" = 0 ] || { echo "$p not root-owned"; exit 1; }; done'
check "storage/ skeleton exists for the chart to seed onto its volume" \
  run "$IMAGE" -c 'for d in storage/framework/cache storage/framework/sessions storage/framework/views storage/logs storage/uploads; do [ -d "$d" ] || { echo "missing $d"; exit 1; }; done'
check "compiled assets present, build-only paths removed" \
  run "$IMAGE" -c '[ -f public/dist/app.js ] && for p in tests dev resources/js resources/sass package.json phpunit.xml .git; do [ ! -e "$p" ] || { echo "$p present"; exit 1; }; done'
check "AWS SDK trimmed to the S3 client" \
  run "$IMAGE" -c 's=vendor/aws/aws-sdk-php/src; [ -d $s/S3 ] && [ ! -d $s/Ec2 ] && [ ! -d $s/DynamoDb ]'
check "no build tools in the runtime image" \
  run "$IMAGE" -c 'for t in git composer gcc cc make; do ! command -v $t >/dev/null 2>&1 || { echo "$t present"; exit 1; }; done'

rm -f /tmp/zz-imgtest.ini
[ $failed -eq 0 ] && echo "IMAGE TESTS PASSED" || echo "IMAGE TESTS FAILED"
exit $failed
