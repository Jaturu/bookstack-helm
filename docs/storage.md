# Upload storage

BookStack stores two kinds of uploads, **images** (embedded in page content
and the image gallery) and **attachments** (files attached to pages). Where they
are kept, and who can fetch them, is set by `bookstack.storageType`.

## Storage modes

| Mode | Images stored in | Images served by | Access check on images | Attachments |
|------|------------------|------------------|------------------------|-------------|
| `local_secure_restricted` *(default)* | `storage/uploads/images` (PVC) | BookStack | Login **and** permission on the page/book the image belongs to | PVC, permission-checked |
| `local_secure` | `storage/uploads/images` (PVC) | BookStack | Login only | PVC, permission-checked |
| `local` | `public/uploads/images` (PVC) | nginx, directly | **None**: anyone with the URL | PVC, permission-checked |
| `s3` | Bucket | The bucket, directly | **None**: images are made public on upload | Bucket (private), fetched by BookStack, permission-checked |

Attachments are always behind BookStack's permission control. The mode only
changes how images are protected.

**System images** (the application logo, and similar) are always stored
publicly in `public/uploads`, whatever the mode, so they display on the login
page. The chart keeps them on the same PVC under the `public-uploads` subPath
and nginx serves them read-only. See [Architecture](architecture.md#volumes).

### Choosing a mode

- Use **`local_secure_restricted`** unless you have a reason not to. Nothing in
  the wiki is reachable without the same permissions BookStack applies to the
  page itself. The trade-off is that an image embedded in a page the viewer
  cannot see will not render for them, even if it is reused elsewhere.
- Use **`local_secure`** if images are reused heavily across books with
  different permissions and "logged in" is protection enough.
- Use **`local`** or **`s3`** only for wikis whose images are not sensitive.
  Image URLs work for anyone who has them.

### Separate modes for images and attachments

`bookstack.storageImageType` and `bookstack.storageAttachmentType` override
`storageType` for one kind of upload. Example: keep images permission-checked
on the PVC while large attachments go to a bucket:

```yaml
bookstack:
  storageType: local_secure_restricted
  storageAttachmentType: s3
  s3:
    bucket: bookstack-attachments
    endpoint: http://rook-ceph-rgw-objectstore.rook-ceph.svc
    existingSecret: bookstack-attachments
```

Attachments in S3 are never made public, so this needs no browser access to
the bucket.

## S3-compatible storage

S3 is used whenever `s3` appears in `storageType`, `storageImageType` or
`storageAttachmentType`. The chart then requires `bookstack.s3.bucket` and
`bookstack.s3.existingSecret`.

| Value | BookStack setting | Notes |
|-------|-------------------|-------|
| `s3.bucket` | `STORAGE_S3_BUCKET` | Required |
| `s3.region` | `STORAGE_S3_REGION` | Any value works for Ceph RGW / MinIO |
| `s3.endpoint` | `STORAGE_S3_ENDPOINT` | Set for anything other than AWS. Setting it also enables path-style addressing |
| `s3.url` | `STORAGE_URL` | Base URL browsers fetch images from; only matters when **images** are on S3 |
| `s3.existingSecret` | `STORAGE_S3_KEY` / `STORAGE_S3_SECRET` | Keys named by `accessKeyIdKey` / `secretAccessKeyKey` |

The default key names, `AWS_ACCESS_KEY_ID` and `AWS_SECRET_ACCESS_KEY`, are
the ones a Rook/Ceph ObjectBucketClaim Secret contains, so an OBC Secret
works without copying keys.

### Example: Rook/Ceph ObjectBucketClaim

Create the claim in the release namespace with a fixed bucket name, so the
name is known when the chart renders:

```yaml
apiVersion: objectbucket.io/v1alpha1
kind: ObjectBucketClaim
metadata:
  name: bookstack-attachments
  namespace: bookstack
spec:
  bucketName: bookstack-attachments
  storageClassName: ceph-bucket
```

Rook creates a Secret and a ConfigMap, both named `bookstack-attachments`. The
ConfigMap's `BUCKET_HOST` and `BUCKET_PORT` give the in-cluster endpoint:

```console
kubectl -n bookstack get configmap bookstack-attachments \
  -o jsonpath='http://{.data.BUCKET_HOST}:{.data.BUCKET_PORT}{"\n"}'
```

Then point the chart at it:

```yaml
bookstack:
  storageAttachmentType: s3
  s3:
    bucket: bookstack-attachments
    endpoint: http://rook-ceph-rgw-objectstore.rook-ceph.svc   # from the command above
    existingSecret: bookstack-attachments
```

### Images on S3

With images on S3 (`storageType: s3` or `storageImageType: s3`), BookStack
uploads each image with a public-read ACL and links to it directly, so:

- the bucket endpoint must be reachable **from users' browsers**, not just
  from the pod. Set `s3.url` to that public address (for example an
  HTTPRoute to RGW);
- anyone with an image URL can fetch it, without logging in.

If either is unacceptable, keep images on the PVC and use S3 for attachments
only.

## Upload size limit

`bookstack.uploadLimitMB` is the single setting for every limit inside the pod.
For a value of *N* the chart sets:

| Layer | Setting | Value |
|-------|---------|-------|
| BookStack | `FILE_UPLOAD_SIZE_LIMIT` | *N* |
| PHP | `upload_max_filesize` | *N* M |
| PHP | `post_max_size` | *N* + 5 M (room for the form around the file) |
| nginx sidecar | `client_max_body_size` | *N* + 5 m |

The default is 50. For example, to allow 200 MB uploads:

```yaml
bookstack:
  uploadLimitMB: 200
```

The one limit outside the chart's control is the **Gateway or Ingress
controller** in front of the pod. It must accept request bodies of at least
*N* + 5 MB. See [Exposure](exposure.md#upload-size) for common controllers.

The PHP limits are written into a chart-generated ini file mounted at
`/etc/bookstack/php.d`. The image loads that directory after its own
settings. Other PHP settings go in `php.extraIni`, appended to the same file:

```yaml
php:
  extraIni: |
    memory_limit = 512M
    max_execution_time = 300
```

The chart refuses `upload_max_filesize` or `post_max_size` in
`php.extraIni`, so the upload limit is never set in two places.

## Changing modes on an existing wiki

BookStack does not move existing files when the mode changes:

- **`local` → `local_secure` / `local_secure_restricted`:** move
  `public/uploads/images` to `storage/uploads/images` on the PVC, then switch
  the mode. Image URLs stay the same.
- **Local → S3, or S3 → local:** copy the files to the new location with the
  same relative paths, then switch the mode. BookStack stores image paths, not
  full URLs.

Take a backup first (see [Database](database.md#backup-and-restore)). The PVC
paths are `storage/` and `public-uploads/` at the root of the volume.
