# Single source of the BookStack version: appVersion in Chart.yaml.
# Recipes use ">" instead of tabs (paste-safe); requires GNU make 3.82+.
.RECIPEPREFIX = >

CHART       := charts/bookstack
VERSION     := $(shell awk -F'"' '/^appVersion:/ {print $$2}' $(CHART)/Chart.yaml)
IMAGE       ?= ghcr.io/jaturu/bookstack
LOCAL_TAG   ?= bookstack:dev

.PHONY: version image lint docs docs-check scan \
        test test-unit test-schema test-scripts lint-files \
        test-image test-install test-upgrade test-all

version:            ## Print the BookStack version from Chart.yaml
> @echo $(VERSION)

image:              ## Build the image locally as $(LOCAL_TAG) and $(IMAGE):$(VERSION)
> @test -n "$(VERSION)" || { echo "appVersion not found in $(CHART)/Chart.yaml" >&2; exit 1; }
> docker build --build-arg BOOKSTACK_VERSION=$(VERSION) -t $(LOCAL_TAG) -t $(IMAGE):$(VERSION) image/

lint:               ## helm lint with the one required value
> helm lint $(CHART) --set bookstack.appUrl=https://wiki.example.com

docs:               ## Regenerate the chart README from values.yaml
> helm-docs --chart-search-root charts

docs-check: docs    ## Fail if the committed chart README is out of date
> git diff --exit-code -- $(CHART)/README.md

# ---------------------------------------------------------------- tests

test: lint test-unit test-schema   ## Fast checks: no image, no cluster

test-unit:          ## Template unit tests (helm-unittest plugin)
> helm unittest $(CHART)

test-schema:        ## Validate rendered scenarios with kubeconform
> tests/schema.sh

test-image: image   ## Build the image and run its contract tests
> IMAGE=$(LOCAL_TAG) tests/image-test.sh

test-install:       ## End-to-end install on a throwaway kind cluster
> tests/install.sh

test-upgrade:       ## Install the latest published release, upgrade to this checkout
> FROM_PUBLISHED=1 tests/install.sh

test-scripts:       ## Release-report script tests + ruff (pip install -r requirements-dev.txt)
> python3 -m pytest -q
> ruff check scripts tests/scripts

lint-files:         ## shellcheck the test scripts, hadolint the Dockerfile
> shellcheck -S warning tests/*.sh
> hadolint image/Dockerfile

scan: image         ## The release gates, locally: fixable High+ findings (Grype + Trivy)
> grype --config .grype-ignore.yaml --only-fixed --fail-on high $(LOCAL_TAG)
> trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 $(LOCAL_TAG)

test-all: test lint-files test-scripts test-image test-install test-upgrade   ## Everything
