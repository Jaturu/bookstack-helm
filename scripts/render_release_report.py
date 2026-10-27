#!/usr/bin/env python3
"""Render the release report published with each version.

Reads the SBOM and scan reports produced per platform and writes the markdown
body of the GitHub Release. The raw JSON ships alongside as release assets, so
this summarizes rather than reproduces.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

# Most severe first. Grype and Trivy both use these names, Trivy in uppercase.
SEVERITY_ORDER = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")
_SUBSECOND = re.compile(r"(\.\d{6})\d+")


@dataclass
class PlatformSummary:
    slug: str
    digest: str
    sbom: dict
    grype: dict
    trivy: dict


def cell(value: str) -> str:
    """Make scanner-supplied text safe to place in a markdown table.

    Package names describe whatever is installed in the image, so they are
    untrusted the same way a catalog-supplied filename is. A bare pipe ends
    the column early and raw markup renders on the published page.
    """
    text = _CONTROL_CHARS.sub("", str(value)).replace("\n", " ")
    return html.escape(text, quote=False).replace("|", "\\|")


def normalize_timestamp(value: str) -> str:
    """Render a scanner timestamp as a UTC minute.

    Trivy emits nine fractional digits, which fromisoformat rejects before
    3.12, and Grype emits the runner's local offset. Anything unparseable is
    returned as-is, because a format change should not cost the whole report.
    """
    if not value:
        return ""
    candidate = _SUBSECOND.sub(r"\1", value.replace("Z", "+00:00"))
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return value
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _ordered(counts: dict[str, int]) -> list[tuple[str, int]]:
    def rank(name: str) -> int:
        try:
            return SEVERITY_ORDER.index(name)
        except ValueError:
            return len(SEVERITY_ORDER)

    return sorted(counts.items(), key=lambda kv: (rank(kv[0]), kv[0]))


def summarize_sbom(doc: dict) -> dict:
    counts = Counter(c.get("type", "unknown") for c in doc.get("components") or [])
    return {"total": sum(counts.values()), "by_type": dict(counts)}


def _package_label(name: str, version: str) -> str:
    return f"{name} {version}".strip() or "unknown"


def _group_findings(rows: list[tuple[str, str, str, str]]) -> list[dict]:
    """Collapse one CVE hitting several packages into a single entry.

    Three Alpine packages sharing one busybox CVE is one problem, and three
    rows read as three.
    """
    grouped: dict[str, dict] = {}
    for vuln_id, severity, package, fix in rows:
        entry = grouped.setdefault(
            vuln_id,
            {"id": vuln_id, "severity": severity, "packages": [], "fix": ""},
        )
        if package not in entry["packages"]:
            entry["packages"].append(package)
        if fix and not entry["fix"]:
            entry["fix"] = fix

    def rank(entry: dict) -> tuple[int, str]:
        try:
            return (SEVERITY_ORDER.index(entry["severity"]), entry["id"])
        except ValueError:
            return (len(SEVERITY_ORDER), entry["id"])

    for entry in grouped.values():
        entry["packages"].sort()
    return sorted(grouped.values(), key=rank)


def summarize_grype(doc: dict) -> dict:
    """Active findings and suppressed ones, kept apart.

    A rule in .grype-ignore.yaml moves a match to ignoredMatches. It stays in
    the report so the reader can see what was allowed and why.
    """
    counts: Counter[str] = Counter()
    fixable: Counter[str] = Counter()
    rows: list[tuple[str, str, str, str]] = []
    for match in doc.get("matches") or []:
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        severity = vuln.get("severity") or "Unknown"
        counts[severity] += 1
        versions = (vuln.get("fix") or {}).get("versions") or []
        # Fixable means a fix version exists to move to. Debian's won't-fix
        # and not-yet-fixed findings list none.
        if versions:
            fixable[severity] += 1
        rows.append(
            (
                vuln.get("id") or "unknown",
                severity,
                _package_label(
                    artifact.get("name") or "", artifact.get("version") or ""
                ),
                ", ".join(versions),
            )
        )

    suppressed = []
    for match in doc.get("ignoredMatches") or []:
        vuln = match.get("vulnerability") or {}
        artifact = match.get("artifact") or {}
        rules = match.get("appliedIgnoreRules") or []
        suppressed.append(
            {
                "id": vuln.get("id") or "unknown",
                "severity": vuln.get("severity") or "Unknown",
                "package": artifact.get("name") or "unknown",
                "version": artifact.get("version") or "",
                "rules": [r.get("vulnerability") for r in rules if r.get("vulnerability")],
                # The reason carries the tracking issue, set in .grype-ignore.yaml.
                "reason": next((r.get("reason") for r in rules if r.get("reason")), ""),
                # A suppression justified by "no fix on our line" stops being
                # justified when a fix appears, so the versions have to show.
                "fix": ", ".join((vuln.get("fix") or {}).get("versions") or []),
            }
        )
    descriptor = doc.get("descriptor") or {}
    # The database date bounds what could have been known at scan time. v0.116
    # reports it under db.status.built, older versions used a flat db.built.
    database = descriptor.get("db") or {}
    built = (database.get("status") or {}).get("built") or database.get("built") or ""
    return {
        "by_severity": dict(counts),
        "fixable_by_severity": dict(fixable),
        "suppressed": suppressed,
        "findings": _group_findings(rows),
        "scanned": normalize_timestamp(descriptor.get("timestamp") or ""),
        "db_built": normalize_timestamp(built),
    }


def summarize_trivy(doc: dict) -> dict:
    """Trivy omits Vulnerabilities entirely on a clean target rather than
    emitting an empty list, so an absent key is a pass, not missing data."""
    counts: Counter[str] = Counter()
    fixable: Counter[str] = Counter()
    rows: list[tuple[str, str, str, str]] = []
    for result in doc.get("Results") or []:
        for vuln in result.get("Vulnerabilities") or []:
            severity = (vuln.get("Severity") or "unknown").capitalize()
            counts[severity] += 1
            if vuln.get("FixedVersion"):
                fixable[severity] += 1
            rows.append(
                (
                    vuln.get("VulnerabilityID") or "unknown",
                    severity,
                    _package_label(
                        vuln.get("PkgName") or "", vuln.get("InstalledVersion") or ""
                    ),
                    vuln.get("FixedVersion") or "",
                )
            )
    return {
        "by_severity": dict(counts),
        "fixable_by_severity": dict(fixable),
        "findings": _group_findings(rows),
        "scanned": normalize_timestamp(doc.get("CreatedAt") or ""),
    }


def summarize_platform(
    slug: str, digest: str, sbom: dict, grype: dict, trivy: dict
) -> PlatformSummary:
    return PlatformSummary(
        slug=slug,
        digest=digest,
        sbom=summarize_sbom(sbom),
        grype=summarize_grype(grype),
        trivy=summarize_trivy(trivy),
    )


def _findings_line(counts: dict[str, int]) -> str:
    if not counts:
        return "No findings."
    return ", ".join(f"{count} {name}" for name, count in _ordered(counts))


def render_report(
    tag: str, index_digest: str, summaries: list[PlatformSummary]
) -> str:
    out: list[str] = []
    out.append(f"# {tag}")
    out.append("")
    out.append(f"Manifest list: `{index_digest}`")
    out.append("")
    out.append(
        "Scans below gate the release. The full CycloneDX SBOM and the raw "
        "Grype and Trivy JSON are attached as assets, and to the platform "
        "digests in the registry as OCI referrers."
    )
    out.append("")
    out.append(
        "Findings are a snapshot taken when this release was built. They do "
        "not change afterwards, so a later advisory against these same "
        "packages will not appear here. Neither this page nor the registry "
        "attachments are signed."
    )

    for summary in summaries:
        out.append("")
        out.append(f"## {summary.slug}")
        out.append("")
        out.append(f"Image digest: `{summary.digest}`")

        scanned = summary.grype.get("scanned") or summary.trivy.get("scanned")
        if scanned:
            line = f"Scanned {scanned}"
            if summary.grype.get("db_built"):
                line += f", vulnerability database built {summary.grype['db_built']}"
            out.append("")
            out.append(f"{line}.")
        out.append("")

        components = summary.sbom
        out.append(f"SBOM: {components['total']} components")
        if components["by_type"]:
            out.append("")
            out.append("| Component type | Count |")
            out.append("|---|---|")
            for name, count in sorted(components["by_type"].items()):
                out.append(f"| {cell(name)} | {count} |")

        out.append("")
        out.append("| Scanner | Findings |")
        out.append("|---|---|")
        out.append(f"| Grype | {_findings_line(summary.grype['by_severity'])} |")
        out.append(f"| Trivy | {_findings_line(summary.trivy['by_severity'])} |")

        for scanner, findings in (
            ("Grype", summary.grype["findings"]),
            ("Trivy", summary.trivy["findings"]),
        ):
            if not findings:
                continue
            out.append("")
            out.append(f"{scanner} findings:")
            out.append("")
            out.append("| CVE | Severity | Packages | Fixed in |")
            out.append("|---|---|---|---|")
            for item in findings:
                packages = ", ".join(cell(p) for p in item["packages"])
                fix = cell(item["fix"]) if item["fix"] else "No fix available"
                out.append(
                    f"| {cell(item['id'])} | {cell(item['severity'])} "
                    f"| {packages} | {fix} |"
                )

        if summary.grype["suppressed"]:
            out.append("")
            out.append("Suppressed by `.grype-ignore.yaml`:")
            out.append("")
            out.append("| CVE | Severity | Package | Reason |")
            out.append("|---|---|---|---|")
            for item in summary.grype["suppressed"]:
                package = item["package"]
                if item["version"]:
                    package = f"{package} {item['version']}"
                reason = item["reason"] or "No reason recorded"
                out.append(
                    f"| {cell(item['id'])} | {cell(item['severity'])} "
                    f"| {cell(package)} | {cell(reason)} |"
                )

    out.append("")
    return "\n".join(out)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--index-digest", required=True)
    parser.add_argument(
        "--reports-dir",
        required=True,
        type=Path,
        help="directory holding sbom/grype/trivy JSON per platform",
    )
    parser.add_argument(
        "--platform",
        action="append",
        required=True,
        metavar="SLUG=DIGEST",
        help="repeatable, e.g. linux-amd64=sha256:...",
    )
    parser.add_argument(
        "--expect-platforms",
        type=int,
        help="fail unless exactly this many platforms were rendered",
    )
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)

    summaries = []
    for entry in args.platform:
        slug, _, digest = entry.partition("=")
        if not slug or not digest:
            parser.error(f"expected SLUG=DIGEST, got {entry!r}")
        summaries.append(
            summarize_platform(
                slug=slug,
                digest=digest,
                sbom=_load(args.reports_dir / f"sbom.cyclonedx.{slug}.json"),
                grype=_load(args.reports_dir / f"grype-report.{slug}.json"),
                trivy=_load(args.reports_dir / f"trivy-report.{slug}.json"),
            )
        )

    # The reports artifact uploads with if-no-files-found: warn, so a lost
    # architecture arrives here as a shorter list rather than as an error.
    if args.expect_platforms is not None and len(summaries) != args.expect_platforms:
        parser.error(
            f"expected {args.expect_platforms} platforms, rendered "
            f"{len(summaries)}: {[s.slug for s in summaries]}"
        )

    body = render_report(args.tag, args.index_digest, summaries)
    if args.output:
        args.output.write_text(body)
    else:
        sys.stdout.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
