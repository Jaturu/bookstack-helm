#!/bin/sh
# Runs a command in the scanners image, pinned by SCANNERS_REF, on the current directory.
set -eu
: "${SCANNERS_REF:?SCANNERS_REF must name the scanners image by digest}"
set -- --rm --user "$(id -u):$(id -g)" -e HOME=/tmp -v "$PWD:/work" -w /work "$SCANNERS_REF" "$@"
# Registry credentials from docker login, read-only, so image scans pull authenticated.
if [ -f "$HOME/.docker/config.json" ]; then
  set -- -e DOCKER_CONFIG=/docker -v "$HOME/.docker:/docker:ro" "$@"
fi
exec docker run "$@"
