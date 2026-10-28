# Installing

A walkthrough for a production install behind a Gateway API gateway, from an
empty namespace to the first login. It assumes a Gateway with an HTTPS
listener and a default StorageClass; [Exposure](exposure.md) covers Ingress
instead.

## 1. Namespace

Create the namespace with the `restricted` Pod Security Standard enforced.
Every container in the chart, MariaDB included, runs under it.

```console
kubectl create namespace bookstack
kubectl label namespace bookstack pod-security.kubernetes.io/enforce=restricted
```

## 2. Values

Start from the chart's own defaults, so every setting and its documentation is
in front of you:

```console
helm show values oci://ghcr.io/jaturu/charts/bookstack --version <chart version> > values.yaml
```

The settings a typical install changes:

```yaml
image:
  tag: v26.09.2-2                  # pin a build; the default follows <appVersion>

bookstack:
  appUrl: https://wiki.example.com
  trustedProxies: "10.244.0.0/16"  # the gateway's pod network
  timezone: America/New_York

persistence:
  storageClass: ""                 # empty = the cluster default

mariadb:
  persistence:
    storageClass: ""

httpRoute:
  enabled: true
  parentRefs:
    - name: my-gateway
      namespace: gateway-system
      sectionName: https
  hostnames:
    - wiki.example.com
```

- `appUrl` must match the hostname users type, including `https://`.
  BookStack builds every link from it.
- `trustedProxies` is what lets BookStack see the original scheme and client
  address. See [Trusted proxies](exposure.md#trusted-proxies).
- Image tags of the form `<BookStack version>-<build>` are immutable; the bare
  `<BookStack version>` tag moves to each new build. See
  [Supply chain](supply-chain.md).

## 3. DNS and TLS

Point the hostname at the gateway, for example a CNAME to the gateway's own
name. TLS is configured on the Gateway listener, not in this chart; a
wildcard certificate there covers BookStack without a certificate of its own.

## 4. Validate before installing

Render the chart and have the API server validate every object without
creating anything. The server-side dry run applies the namespace's Pod
Security admission and checks the HTTPRoute against the installed Gateway API
CRDs:

```console
helm template bookstack oci://ghcr.io/jaturu/charts/bookstack --version <chart version> \
  -n bookstack -f values.yaml > rendered.yaml
sed -n '/^---$/,$p' rendered.yaml | kubectl apply -n bookstack --dry-run=server -f -
```

Every line should end in `created (server dry run)`, with no
`would violate PodSecurity` warnings.

> **Helm 4 and OCI charts.** When `helm template` pulls a chart from an OCI
> registry, Helm 4 writes its `Pulled:` and `Digest:` lines to standard
> output, ahead of the manifests. Piped straight into `kubectl`, they fail
> with `apiVersion not set, kind not set`. The `sed` above drops everything
> before the first document. `helm install` and `helm upgrade` are not
> affected.

## 5. Install

```console
helm install bookstack oci://ghcr.io/jaturu/charts/bookstack --version <chart version> \
  -n bookstack -f values.yaml --wait --timeout 10m
helm test bookstack -n bookstack
```

On a first install the built-in MariaDB initialises for a minute or so. The
`wait-for-database` init container holds the pod until it accepts a login,
then `migrate` creates the schema. See
[Startup sequence](architecture.md#startup-sequence).

Check the route end to end. A `302` to `/login` is the expected answer for a
visitor who is not signed in, and the `https://` in it confirms the trusted
proxies setting:

```console
curl -sS -o /dev/null -w '%{http_code} %{redirect_url}\n' https://wiki.example.com/
```

A certificate error here, with a private CA, means this machine does not
trust that CA yet; the deployment itself is fine. `curl -k` checks the route
alone.

## 6. First login

1. Sign in as `admin@admin.com` / `password` and change both under
   **My Account** immediately. See [First login](database.md#first-login).
2. Under **Settings → Registration**, leave **Allow registration** off unless
   users should create their own accounts. Create accounts under
   **Settings → Users** instead.
3. Under **Settings → Customization**, set the application name, logo,
   colours and homepage.

## 7. Afterwards

- **Email** for password resets, invitations and notifications:
  [Email](email.md).
- **Backups** of the database, uploads and `APP_KEY`:
  [Backup and restore](database.md#backup-and-restore). `APP_KEY` and the
  database passwords are generated inside the cluster; keep a copy elsewhere.
- **Upgrades:** [Upgrading](upgrading.md).
