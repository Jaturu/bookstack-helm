# Security status

Action needed: 1 High or Critical finding(s) with a fix available against the current release.

Release `v26.09.2-4`, published as `ghcr.io/jaturu/bookstack:v26.09.2-4` and `ghcr.io/jaturu/bookstack:latest`.
Manifest list `sha256:509d9fcb2c5e4ba96e95b673df2478057367b9de9e746b18d2006483672be082`.
Re-scanned 2026-11-09 16:31 UTC against a vulnerability database built 2026-11-08 06:19 UTC.

This page is regenerated on a schedule from the CycloneDX SBOM attached to the published image, so it reflects what the scanners know now rather than what they knew at build time. It is generated output and is not signed. The per-release pages under Releases are the build-time snapshots and do not change. Counts are of distinct vulnerabilities: one reported by both scanners, or on several platforms, is counted once, at the higher severity either scanner gives.

## linux-amd64

Image digest: `sha256:d07a8ae50bad038a732af39df227dc584037fdcb179d8f49eb80d731f6b5b7c5`

| CVE | Severity | Packages | Fixed in |
|---|---|---|---|
| CVE-2026-4738 | Critical | zlib 1.3.2-r1 | 1.4-r0 |
| CVE-2025-60876 | Medium | busybox 1.37.0-r31, busybox-binsh 1.37.0-r31, ssl_client 1.37.0-r31 | No fix available |
| CVE-2026-45070 | Medium | symfony/mime v7.4.19 | 5.4.0, 6.2.0, 7.3.0, 7.4.0, 8.1.0, 3.0.0, 5.0.0, 5.4.55, 6.4.49, 5.3.0, 6.1.0, 6.3.0, 6.4.0, 7.1.0, 7.2.0, 8.1.10, 4.0.0, 5.1.0, 5.2.0, 7.4.22 |
| CVE-2026-118514 | Unknown | symfony/http-foundation v7.4.21 | 5.0.0, 5.2.0, 5.4.0, 6.4.0, 7.3.0, 8.1.11, 4.0.0, 5.1.0, 5.3.0, 5.4.56, 6.2.0, 6.3.0, 7.1.0, 8.1.0, 3.0.0, 7.2.0, 7.4.23, 6.1.0, 6.4.50, 7.4.0 |
| CVE-2026-118516 | Unknown | symfony/routing v7.4.21 | 7.3.0, 7.4.23, 8.1.11, 4.3.0, 5.0.0, 5.4.56, 7.4.0, 4.2.0, 6.4.0, 8.1.0, 6.2.0, 6.3.0, 4.4.0, 5.1.0, 5.2.0, 5.3.0, 6.1.0, 7.2.0, 5.4.0, 6.4.50, 7.1.0 |

## linux-arm64

Image digest: `sha256:903de958c81ac3be188caecfd31f30a3935270f02fa4132f292454d47da6d02f`

| CVE | Severity | Packages | Fixed in |
|---|---|---|---|
| CVE-2026-4738 | Critical | zlib 1.3.2-r1 | 1.4-r0 |
| CVE-2025-60876 | Medium | busybox 1.37.0-r31, busybox-binsh 1.37.0-r31, ssl_client 1.37.0-r31 | No fix available |
| CVE-2026-45070 | Medium | symfony/mime v7.4.19 | 5.4.0, 6.2.0, 7.3.0, 7.4.0, 8.1.0, 3.0.0, 5.0.0, 5.4.55, 6.4.49, 5.3.0, 6.1.0, 6.3.0, 6.4.0, 7.1.0, 7.2.0, 8.1.10, 4.0.0, 5.1.0, 5.2.0, 7.4.22 |
| CVE-2026-118514 | Unknown | symfony/http-foundation v7.4.21 | 5.0.0, 5.2.0, 5.4.0, 6.4.0, 7.3.0, 8.1.11, 4.0.0, 5.1.0, 5.3.0, 5.4.56, 6.2.0, 6.3.0, 7.1.0, 8.1.0, 3.0.0, 7.2.0, 7.4.23, 6.1.0, 6.4.50, 7.4.0 |
| CVE-2026-118516 | Unknown | symfony/routing v7.4.21 | 7.3.0, 7.4.23, 8.1.11, 4.3.0, 5.0.0, 5.4.56, 7.4.0, 4.2.0, 6.4.0, 8.1.0, 6.2.0, 6.3.0, 4.4.0, 5.1.0, 5.2.0, 5.3.0, 6.1.0, 7.2.0, 5.4.0, 6.4.50, 7.1.0 |
