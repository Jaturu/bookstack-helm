# Exposing BookStack

The chart's Service speaks plain HTTP to the nginx sidecar. TLS terminates at
whatever sits in front: a Gateway API `Gateway` (via `httpRoute`) or an
Ingress controller (via `ingress`). Either or both can be enabled.

Whichever you use, three settings must agree:

| Setting | Must match |
|---------|------------|
| `bookstack.appUrl` | The exact public URL users type, with scheme, no trailing slash |
| `httpRoute.hostnames` / `ingress.hosts` | The host part of `appUrl` |
| `bookstack.trustedProxies` | The network your gateway or controller pods run in |

BookStack builds every link and redirect from `appUrl`. A mismatch typically
shows as redirect loops, broken CSS, or links to the wrong host.

## Gateway API (HTTPRoute)

Requires the Gateway API CRDs (`gateway.networking.k8s.io/v1`) and a Gateway
with a listener that accepts routes from the release namespace.

```yaml
bookstack:
  appUrl: https://wiki.example.com
  trustedProxies: "10.244.0.0/16"   # pod network of the gateway's data plane

httpRoute:
  enabled: true
  parentRefs:
    - name: my-gateway
      namespace: gateway-system
      sectionName: https              # the HTTPS listener
  hostnames:
    - wiki.example.com
```

- TLS is configured on the Gateway listener, not in this chart. A wildcard
  certificate on the listener (e.g. `*.example.com`) covers BookStack with no
  per-app certificate.
- Set `sectionName` to attach only to the HTTPS listener. If the Gateway also
  has an HTTP listener with a redirect route, plain-HTTP requests are
  redirected before they reach BookStack.
- Check the route was accepted:

```console
  kubectl -n bookstack get httproute wiki-bookstack \
    -o jsonpath='{range .status.parents[*]}{.parentRef.name}: {range .conditions[*]}{.type}={.status} {end}{"\n"}{end}'
```

  Both `Accepted=True` and `ResolvedRefs=True` are expected.

## Ingress

```yaml
bookstack:
  appUrl: https://wiki.example.com
  trustedProxies: "10.244.0.0/16"   # pod network of the ingress controller

ingress:
  enabled: true
  className: nginx
  annotations:
    cert-manager.io/cluster-issuer: letsencrypt
  hosts:
    - wiki.example.com
  tls:
    - secretName: wiki-tls
      hosts:
        - wiki.example.com
```

The chart renders one rule per host, all with the same `path` / `pathType`
(`/`, `Prefix`) pointing at the Service's `http` port. Annotations are passed
through unchanged, so controller-specific features (TLS issuers, auth, body
size) go there.

## Trusted proxies

Between the user and PHP there are two hops: the gateway or Ingress
controller, then the nginx sidecar. The sidecar passes requests to php-fpm
over FastCGI and does not add a proxy hop of its own. PHP sees the
**gateway pod's address** as the client, with the original scheme and client
IP in `X-Forwarded-Proto` / `X-Forwarded-For`.

BookStack only honours those headers from addresses in
`bookstack.trustedProxies` (`APP_PROXIES`). Set it to the CIDR your gateway or
controller pods use, typically the cluster pod network:

```yaml
bookstack:
  trustedProxies: "10.244.0.0/16"
```

`"*"` trusts any source. Use it only if nothing but the gateway can reach the
pod, for example when a NetworkPolicy restricts ingress to the gateway's
namespace.

When this is wrong:

- **Not set:** BookStack sees `http://` from the gateway, while `appUrl` says
  `https://`. Links are still built from `appUrl`, but audit logs record the
  gateway's IP instead of the user's, and IP-based features (login throttling)
  apply to everyone at once.
- **Client IPs still wrong after setting it:** the gateway itself may be
  receiving SNATed traffic. Its LoadBalancer Service needs
  `externalTrafficPolicy: Local` for the real client address to reach it.

## Upload size

The chart derives every limit inside the pod from `bookstack.uploadLimitMB`
(see [Storage](storage.md#upload-size-limit)). The gateway or controller in
front must also accept request bodies of at least **`uploadLimitMB` + 5 MB**.
Otherwise large uploads fail before reaching BookStack, usually as an HTTP 413
from the proxy.

| Front end | Default body limit | Where to raise it |
|-----------|--------------------|-------------------|
| ingress-nginx | 1 MB | annotation `nginx.ingress.kubernetes.io/proxy-body-size: 55m` |
| NGINX Ingress Controller (F5) | 1 MB | annotation `nginx.org/client-max-body-size: 55m` |
| Envoy Gateway | no limit on streamed request bodies by default | only relevant if a policy enables request buffering |
| Traefik | no limit by default | only relevant if a Buffering middleware is attached |

Check your controller's documentation for its current default; the values
above are the commonly shipped ones.

## Restricting access

The chart doesn't add access control in front of BookStack. To limit who can
reach the wiki at the network level:

- attach the route only to an internal Gateway or IngressClass, so the wiki is
  never published externally;
- use your gateway's own authorisation or IP-allowlist policy;
- add a NetworkPolicy in the release namespace that admits traffic to the
  BookStack pod's port 8080 only from the gateway's namespace. With that in
  place `trustedProxies: "*"` is also safe.

Inside the wiki, access is governed by BookStack's roles and permissions, and
by `AUTH_METHOD` if you use OIDC, SAML or LDAP.
