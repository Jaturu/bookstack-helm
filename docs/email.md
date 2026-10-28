# Email

BookStack sends email for password resets, user invitations, email
confirmation and notifications. Nothing is configured by default, so until
these settings are in place every one of those fails.

Mail settings are plain BookStack `.env` keys, passed through
`bookstack.env`. The password is a secret, so it comes from a Kubernetes
Secret through `bookstack.extraEnv` instead; `bookstack.env` is rendered into
a ConfigMap.

## Authenticated SMTP

For a mail provider or an organisation's mail server, typically port 587
with STARTTLS:

```console
kubectl -n bookstack create secret generic bookstack-smtp \
  --from-literal=password='<SMTP password>'
```

```yaml
bookstack:
  env:
    MAIL_DRIVER: smtp
    MAIL_HOST: smtp.example.com
    MAIL_PORT: "587"
    MAIL_ENCRYPTION: tls
    MAIL_USERNAME: wiki@example.com
    MAIL_FROM: wiki@example.com
    MAIL_FROM_NAME: Wiki
  extraEnv:
    - name: MAIL_PASSWORD
      valueFrom:
        secretKeyRef:
          name: bookstack-smtp
          key: password
```

- `MAIL_ENCRYPTION: tls` requires TLS or STARTTLS. Port 465 always uses TLS.
- `MAIL_FROM` must be an address the server allows that user to send as, and
  the domain should have SPF and DKIM records for the server, or the mail is
  likely to be marked as spam.
- Quote the port: `bookstack.env` values must be strings.

## Through an in-cluster relay

When a cluster runs an SMTP relay for all its applications (for example a
Postfix relay that forwards to the organisation's mail service), BookStack
needs no credentials of its own:

```yaml
bookstack:
  env:
    MAIL_DRIVER: smtp
    MAIL_HOST: smtp-relay.mail.svc.cluster.local
    MAIL_PORT: "25"
    MAIL_ENCRYPTION: "null"
    MAIL_FROM: wiki@example.com
    MAIL_FROM_NAME: Wiki
```

With `MAIL_ENCRYPTION: "null"`, BookStack still uses STARTTLS if the relay
offers it. If the relay presents a certificate from a private CA that the
image does not trust, `MAIL_VERIFY_SSL: "false"` skips verification. Inside
the cluster that is usually acceptable; across a network it is not.

## Applying and testing

Apply the values with `helm upgrade`. The ConfigMap change restarts the
BookStack pod. Then, in BookStack, go to **Settings → Maintenance → Send a
Test Email**: it sends to the signed-in user and shows any error the mail
server returned.

The full list of mail settings is in BookStack's
[email documentation](https://www.bookstackapp.com/docs/admin/email-webhooks/).
