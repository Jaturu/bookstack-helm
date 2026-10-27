#!/usr/bin/env bash
# End-to-end install test on a throwaway kind cluster:
#   build image -> load into kind -> install (restricted PodSecurity) ->
#   helm test -> upgrade (secrets stable, pod rolls) -> helm test ->
#   uninstall (data-bearing resources kept).
#
# Uses its own kubeconfig file, so it never touches your current context.
# Needs: docker, kind, kubectl, helm, make.
#
#   tests/install.sh                  # build, test, delete cluster
#   KEEP_CLUSTER=1 tests/install.sh   # keep the cluster afterwards for poking
#   SKIP_BUILD=1 tests/install.sh     # reuse an already built image
#   FROM_PUBLISHED=1 tests/install.sh # upgrade test: install the latest
#                                     # published chart + image from GHCR,
#                                     # then upgrade to this checkout
#   PUBLISHED_VERSION=0.1.0           # with FROM_PUBLISHED, pin the start
set -euo pipefail

cd "$(dirname "$0")/.."
CLUSTER=${CLUSTER:-bookstack-test}
NS=bookstack-test
REL=wiki
CHART=charts/bookstack
VALUES=$CHART/ci/default-values.yaml
VERSION=$(make -s version)
IMAGE=ghcr.io/jaturu/bookstack:$VERSION
PUBLISHED_CHART=oci://ghcr.io/jaturu/charts/bookstack

for tool in docker kind kubectl helm make; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 2; }
done

export KUBECONFIG
KUBECONFIG=$(mktemp)
step() { printf '\n==> %s\n' "$*"; }
fail() { echo "FAIL: $*" >&2; exit 1; }

diagnostics() {
  step "diagnostics"
  kubectl -n "$NS" get pods,pvc,secrets -o wide || true
  for pod in $(kubectl -n "$NS" get pods -o name 2>/dev/null); do
    kubectl -n "$NS" describe "$pod" | tail -25 || true
    for c in $(kubectl -n "$NS" get "$pod" -o jsonpath='{.spec.initContainers[*].name} {.spec.containers[*].name}'); do
      echo "--- $pod/$c"; kubectl -n "$NS" logs "$pod" -c "$c" --tail=40 || true
    done
  done
}
cleanup() {
  rc=$?
  [ $rc -ne 0 ] && diagnostics
  if [ -z "${KEEP_CLUSTER:-}" ]; then
    kind delete cluster --name "$CLUSTER" >/dev/null 2>&1 || true
  else
    echo; echo "Cluster kept. Use it with: kind export kubeconfig --name $CLUSTER"
  fi
  rm -f "$KUBECONFIG"
  [ $rc -eq 0 ] && echo && echo "INSTALL TEST PASSED"
  exit $rc
}
trap cleanup EXIT

if [ -z "${SKIP_BUILD:-}" ]; then
  step "build $IMAGE"
  make -s image
fi

step "kind cluster $CLUSTER"
if kind get clusters | grep -qx "$CLUSTER"; then
  kind export kubeconfig --name "$CLUSTER"
else
  kind create cluster --name "$CLUSTER" --wait 120s
fi
# In the upgrade test the published image must be what the first install
# runs, so the local image (same tag) is loaded only right before upgrading.
load_local_image() { kind load docker-image "$IMAGE" --name "$CLUSTER"; }
[ -n "${FROM_PUBLISHED:-}" ] || load_local_image

step "namespace with restricted PodSecurity enforced"
kubectl create namespace "$NS" --dry-run=client -o yaml | kubectl apply -f -
kubectl label namespace "$NS" --overwrite \
  pod-security.kubernetes.io/enforce=restricted \
  pod-security.kubernetes.io/warn=restricted

if [ -n "${FROM_PUBLISHED:-}" ]; then
  step "install the published chart${PUBLISHED_VERSION:+ $PUBLISHED_VERSION} and image"
  helm install "$REL" "$PUBLISHED_CHART" ${PUBLISHED_VERSION:+--version "$PUBLISHED_VERSION"} \
    -n "$NS" -f "$VALUES" --wait --timeout 10m
  helm list -n "$NS"
else
  step "install"
  helm install "$REL" "$CHART" -n "$NS" -f "$VALUES" --wait --timeout 10m
fi

step "helm test"
helm test "$REL" -n "$NS" --logs

step "record secrets and pod"
secret() { kubectl -n "$NS" get secret "$1" -o jsonpath="{.data.$2}"; }
key1=$(secret "$REL-bookstack-app-key" APP_KEY)
pw1=$(secret "$REL-bookstack-mariadb" 'mariadb-password')
pod1=$(kubectl -n "$NS" get pod -l app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.uid}')

if [ -n "${FROM_PUBLISHED:-}" ]; then
  step "load this checkout's image for the upgrade"
  load_local_image
fi

step "upgrade to this checkout, with a config change"
helm upgrade "$REL" "$CHART" -n "$NS" -f "$VALUES" \
  --set bookstack.timezone=America/New_York --wait --timeout 10m
[ "$(secret "$REL-bookstack-app-key" APP_KEY)" = "$key1" ] || fail "APP_KEY changed on upgrade"
[ "$(secret "$REL-bookstack-mariadb" 'mariadb-password')" = "$pw1" ] || fail "DB password changed on upgrade"
pod2=$(kubectl -n "$NS" get pod -l app.kubernetes.io/component=app -o jsonpath='{.items[0].metadata.uid}')
[ "$pod2" != "$pod1" ] || fail "pod did not roll on a ConfigMap change"
echo "secrets unchanged, pod rolled"

step "helm test after upgrade"
helm test "$REL" -n "$NS" --logs

step "uninstall keeps data-bearing resources"
helm uninstall "$REL" -n "$NS" --wait
for r in "secret/$REL-bookstack-app-key" "secret/$REL-bookstack-mariadb" \
         "pvc/$REL-bookstack-data" "pvc/data-$REL-bookstack-mariadb-0"; do
  kubectl -n "$NS" get "$r" >/dev/null || fail "$r was deleted by uninstall"
  echo "kept: $r"
done
