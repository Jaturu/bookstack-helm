#!/usr/bin/env bash
# Render the chart for every scenario in tests/values/ and validate the output
# against the Kubernetes OpenAPI schemas (plus Gateway API CRD schemas) with
# kubeconform. Needs: helm, kubeconform.
#
#   tests/schema.sh                 # all scenarios
#   KUBE_VERSION=1.33.0 tests/schema.sh
set -euo pipefail

cd "$(dirname "$0")/.."
CHART=charts/bookstack
KUBE_VERSION=${KUBE_VERSION:-master}
CRD_SCHEMAS='https://raw.githubusercontent.com/datreeio/CRDs-catalog/main/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json'

for tool in helm kubeconform; do
  command -v "$tool" >/dev/null || { echo "missing: $tool" >&2; exit 2; }
done

fail=0
for values in tests/values/*.yaml; do
  name=$(basename "$values" .yaml)
  printf '%-14s ' "$name"
  if ! out=$(helm template bookstack "$CHART" --namespace bookstack -f "$values" 2>&1); then
    echo "RENDER FAILED"; echo "$out" | sed 's/^/    /'; fail=1; continue
  fi
  if res=$(kubeconform -strict -summary -kubernetes-version "$KUBE_VERSION" \
             -schema-location default -schema-location "$CRD_SCHEMAS" - <<<"$out" 2>&1); then
    echo "$res" | tail -1
  else
    echo "INVALID"; echo "$res" | sed 's/^/    /'; fail=1
  fi
done
exit $fail
