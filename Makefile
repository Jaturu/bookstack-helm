# Single source of the BookStack version: appVersion in Chart.yaml.
# Recipes use ">" instead of tabs (paste-safe); requires GNU make 3.82+.
.RECIPEPREFIX = >

CHART       := charts/bookstack
VERSION     := $(shell awk -F'"' '/^appVersion:/ {print $$2}' $(CHART)/Chart.yaml)
IMAGE       ?= ghcr.io/jaturu/bookstack
LOCAL_TAG   ?= bookstack:dev

.PHONY: version image image-test lint docs docs-check

version:            ## Print the BookStack version from Chart.yaml
> @echo $(VERSION)

image:              ## Build the image locally as $(LOCAL_TAG) and $(IMAGE):$(VERSION)
> @test -n "$(VERSION)" || { echo "appVersion not found in $(CHART)/Chart.yaml" >&2; exit 1; }
> docker build --build-arg BOOKSTACK_VERSION=$(VERSION) -t $(LOCAL_TAG) -t $(IMAGE):$(VERSION) image/

image-test: image   ## Smoke-test the built image
> docker run --rm $(LOCAL_TAG) sh -c 'id -u; cat version; php-fpm -t 2>&1 | tail -1; php artisan --version'

lint:               ## helm lint with the one required value
> helm lint $(CHART) --set bookstack.appUrl=https://wiki.example.com

docs:               ## Regenerate the chart README from values.yaml
> helm-docs --chart-search-root charts

docs-check: docs    ## Fail if the committed chart README is out of date
> git diff --exit-code -- $(CHART)/README.md
