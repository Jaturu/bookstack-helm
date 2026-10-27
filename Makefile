# Single source of the BookStack version: appVersion in Chart.yaml.
# Recipes use ">" instead of tabs (paste-safe); requires GNU make 3.82+.
.RECIPEPREFIX = >

CHART       := charts/bookstack
VERSION     := $(shell awk -F'"' '/^appVersion:/ {print $$2}' $(CHART)/Chart.yaml)
IMAGE       ?= ghcr.io/jaturu/bookstack
LOCAL_TAG   ?= bookstack:dev

.PHONY: version image lint docs docs-check \
        test test-unit test-schema test-image test-install test-all

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

test-all: test test-image test-install   ## Everything
