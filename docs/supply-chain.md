# Supply chain

How the image and chart are built and published, what provenance material
ships with them, why the pipeline is shaped this way, and how to verify a
release by hand or from automation. The pipeline follows the same pattern as
[Jaturu/omada-release-watch](https://github.com/Jaturu/omada-release-watch).

## Overview

| Artifact | Published at |
|----------|--------------|
| Image | `ghcr.io/jaturu/bookstack`, multi-platform (`linux/amd64`, `linux/arm64`), each built natively |
| Chart | `https://jaturu.github.io/bookstack-helm` (Helm repo) and `oci://ghcr.io/jaturu/charts/bookstack` |

Both are public; every command below works without an account.

Image tags:

| Tag | Meaning |
|-----|---------|
| `<appVersion>-<build>`, e.g. `v26.09.2-1` | **Immutable** release. Never moved or overwritten |
| `<appVersion>`, e.g. `v26.09.2` | Moves to each rebuild of that BookStack release (security updates). The chart's default |
| `latest` | The newest release |
| `sha-<commit>` | Staging tag written during a release, before signing. Not a release |

Each image release carries:

| Material | Format | Where it lives |
|----------|--------|----------------|
| Signature | Sigstore bundle (keyless) | OCI referrer on the manifest and on each platform image |
| SBOM attestation | in-toto, BuildKit | Attestation manifest inside the image index |
| Provenance attestation | in-toto SLSA, BuildKit | Attestation manifest inside the image index |
| Provenance attestation | in-toto SLSA, GitHub | GitHub attestations API, and OCI referrer on the index |
| SBOM and scan reports | CycloneDX and raw Grype / Trivy JSON | OCI referrer on each platform image, and GitHub Release assets |

The OCI chart is signed the same way. Every image release also has a GitHub
Release, `image-<appVersion>-<build>`, with a rendered summary of the scans.

## The pipeline

Defined in [`.github/workflows/release.yaml`](../.github/workflows/release.yaml),
triggered by a merge to `main` that touches `charts/`, `image/` or
`.grype-ignore.yaml`, or by hand with **force-image** to pick up Alpine
security updates.

`plan` decides whether the image needs building: forced, `image/` or the
ignore file changed, `appVersion` changed, or the `<appVersion>` tag is missing.

Per platform, in `build-platform`:

1. Build for that platform alone and push it by digest, with no tag.
2. Resolve the image manifest digest from the pushed object.
3. Generate a CycloneDX SBOM with Syft against that image.
4. Scan with Grype, applying `.grype-ignore.yaml`, once for a full report and
   once as a gate on fixable High or above.
5. Scan with Trivy, once for a full report and once as a gate on fixable HIGH
   and CRITICAL.
6. Attach the SBOM and both reports to that platform's image digest.

Once, in `publish-image`:

7. Merge the per-platform digests into the staging tag `sha-<commit>`.
8. Scan the source tree, including the rendered Helm chart, for secrets and misconfiguration with Trivy.
9. Sign the manifest and every platform image with keyless cosign, then verify.
10. Record a GitHub provenance attestation for the manifest.
11. Claim the build number as the git tag `image-<appVersion>-<build>`.
12. Promote the manifest digest to `<appVersion>-<build>`, `<appVersion>` and `latest`.
13. Publish the release report as a GitHub Release.

Then `chart` publishes a new chart version to the GitHub release, the
`gh-pages` index and the OCI registry, and signs the OCI chart. An already
published chart version is skipped, so only a `version` bump releases one.

## Why the pipeline is shaped this way

**Native runners instead of emulation.** Each platform builds on a runner of
its own architecture (`ubuntu-24.04`, `ubuntu-24.04-arm`) rather than under
QEMU, so arm64 builds take as long as amd64.

**Scanning per platform.** The two platform images do not contain identical
packages. A scan of a multi-platform reference resolves to the scanner's own
architecture and silently ignores the other, so each platform is scanned on
its own runner and a gate failure on either stops the release.

**Digest-scoped work before any release tag.** Promotion and release tags are
the irreversible parts. Signing depends on external services, so it happens
while only digests are in play; a signing failure leaves no release tag.

**Claiming the build number first.** The number is derived from git tags, so
the git tag is pushed before any registry tag. A later failure leaves a git
tag with no image, which is inert. Claiming it last would let a failure strand
a published image with no tag, after which every retry recomputes the same
number, hits the immutability check, and is refused. The immutability check
only treats a genuine not-found as free; a rate limit, 5xx, DNS failure or
expired credential stops the release.

**Signing recursively, attaching per platform.** Automated consumers resolve
an image reference to the platform digest, because that is what runs.
Signatures and attachments addressed only to the manifest list are invisible
to them. `cosign sign --recursive` covers the manifest and every platform
image, and attachments go on each platform image.

**Keeping both BuildKit attestations and ORAS attachments.** BuildKit
attestations are what `docker buildx imagetools inspect` and Docker Scout read.
Vulnerability reports have no equally well-consumed attestation type, so the
Grype and Trivy reports are ORAS referrers.

**Resolving the image manifest digest.** With attestations enabled, a
single-platform build pushes a small index (image plus attestation). Scanners
and attachments need the image manifest inside it; the merge deliberately uses
the index, because that carries the attestations into the published image.

**Waiting before verification.** The registry does not serve a freshly written
referrer immediately. The verify step retries, bounded by a timeout.

**Gates block on fixable findings only.** A distribution can leave a High or
Critical CVE unfixed for a while, or mark it won't-fix. Nothing in the image
can be upgraded to clear those, so a gate on them would fail a build until
the distribution acts. The gates therefore run with Grype
`only-fixed` and Trivy `--ignore-unfixed`: a release stops only when a fixed
package exists and the image does not have it. A rebuild normally clears that.

Each scanner runs twice: once without the filter for the full report, once
with it as the gate. The full reports keep every finding, unfixed ones
included, and Grype still records suppressed findings under `ignoredMatches`
with the rule that hid them. The release report and status page show them all.

**Reading Alpine scan results.** Alpine's security database mainly records
vulnerabilities that already have a fixed package. Unfixed ones are reported
less consistently than on Debian, which publishes a status for every CVE. Low
counts on the Alpine image therefore reflect both a smaller, faster-patched
package set and less data about unfixed issues; they are not a guarantee that
nothing is open.

**The status page uses the same split.** The weekly verdict turns red only
for High or Critical findings with a fix available. Unfixed High or Critical
findings give a yellow badge and are listed, so they stay visible. A fix
known to either scanner makes a vulnerability fixable.

The page and badge count distinct vulnerabilities. Grype and Trivy on two
platforms name most CVEs four times; each is counted once, at the higher
severity the scanners give it, and each platform's table lists it once.

## Suppressing a finding

Add a rule to [`.grype-ignore.yaml`](../.grype-ignore.yaml) with a `reason`
that names the tracking issue. The rule and reason show up in every release
report and on the status page, so an accepted finding is visible rather than
hidden. Retire the rule when a fix reaches a version the image can move to.
Trivy gates independently and does not read the Grype ignore file.

## Verifying a release by hand

Always work from digests; tags can move.

```console
crane digest ghcr.io/jaturu/bookstack:v26.09.2-1
crane digest --platform linux/amd64 ghcr.io/jaturu/bookstack:v26.09.2-1
```

Signature (works on the manifest digest and on a platform digest):

```console
COSIGN_EXPERIMENTAL=1 cosign verify \
  --certificate-identity-regexp 'https://github.com/Jaturu/bookstack-helm/\.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com \
  ghcr.io/jaturu/bookstack@sha256:<digest>
```

`COSIGN_EXPERIMENTAL=1` makes cosign 3 look for the signature as an OCI
referrer; without it, a correctly signed image can report `no signatures found`.
There is no public key: verification checks the signing certificate against the
workflow identity and the GitHub OIDC issuer.

GitHub provenance:

```console
gh attestation verify oci://ghcr.io/jaturu/bookstack:v26.09.2-1 --owner Jaturu
```

What is attached, and the SBOM and scan reports (on platform digests):

```console
cosign tree ghcr.io/jaturu/bookstack@sha256:<digest>
oras discover ghcr.io/jaturu/bookstack@sha256:<platform digest>
oras pull ghcr.io/jaturu/bookstack@sha256:<platform digest> -o ./out
```

| File | Contents |
|------|----------|
| `sbom.cyclonedx.<platform>.json` | CycloneDX SBOM |
| `grype-report.<platform>.json` | Grype findings, including `ignoredMatches` |
| `trivy-report.<platform>.json` | Trivy findings |

BuildKit attestations:

```console
docker buildx imagetools inspect ghcr.io/jaturu/bookstack:v26.09.2-1 --format '{{ json .SBOM }}'
docker buildx imagetools inspect ghcr.io/jaturu/bookstack:v26.09.2-1 --format '{{ json .Provenance }}'
```

OCI chart signature:

```console
COSIGN_EXPERIMENTAL=1 cosign verify ghcr.io/jaturu/charts/bookstack:0.1.0 \
  --certificate-identity-regexp 'https://github.com/Jaturu/bookstack-helm/\.github/workflows/.*' \
  --certificate-oidc-issuer https://token.actions.githubusercontent.com
```

## Is the current release safe to run today

[`security-status.md`](security-status.md) answers that. The `rescan` workflow
rewrites it weekly (Mondays) and on demand: it pulls the CycloneDX SBOM attached
to each platform of `latest`, re-scans it with Grype and Trivy using the same
`.grype-ignore.yaml`, and commits the page and its badge. A fixable High or
Critical finding turns the run red after the page is committed. The file's git history
records when each finding appeared or went away.

The GitHub Release pages are the opposite: snapshots of what was known at build
time, which never change. Neither those pages nor the ORAS attachments are
signed; the signature covers the image, and the reports are only as trustworthy
as the run that produced them.

## Verifying from automation

| Field | Value |
|-------|-------|
| Certificate identity | `https://github.com/Jaturu/bookstack-helm/.github/workflows/release.yaml@refs/heads/main` |
| Identity regexp | `https://github.com/Jaturu/bookstack-helm/\.github/workflows/.*` |
| OIDC issuer | `https://token.actions.githubusercontent.com` |

Resolve to the platform digest and verify that. In an admission controller
(Sigstore policy-controller, Kyverno), use the identity and issuer above; the
registry is public, and the controller must read OCI referrers rather than only
legacy `.sig` tags. To pin a deployment, set `image.digest` in the chart values.

## Constraints

Keyless signing writes to the public Rekor transparency log, so every release
has an independent public record of its digest and workflow identity.

Release tags `<appVersion>-<build>` are immutable; `<appVersion>` and `latest`
move by design. Freshly written referrers are not served immediately, so
anything verifying moments after a release should retry.
