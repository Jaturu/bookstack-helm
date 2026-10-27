#!/usr/bin/env python3
"""Render the living security status of the current release.

The release report published with a version is a snapshot and never changes.
This page is rewritten on a schedule by re-scanning the SBOM already attached
to the published image, so it answers whether the current release is safe to
run today rather than what was known when it was built.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from scripts.render_release_report import (
    SEVERITY_ORDER,
    PlatformSummary,
    cell,
    summarize_platform,
)

# A finding at or above this level is worth a reader's attention. Everything
# below is the steady state and would make the verdict meaningless.
ACTIONABLE = ("Critical", "High")


def _rank(severity: str) -> int:
    try:
        return SEVERITY_ORDER.index(severity)
    except ValueError:
        return len(SEVERITY_ORDER)


def _merge(findings: list[dict]) -> list[dict]:
    """One entry per vulnerability ID, however many reports name it.

    Two scanners on two platforms report most CVEs four times. Where the
    reports disagree, the entry takes the higher severity and any fix one of
    them knows, because either scanner's gate fails on what it sees.
    """
    merged: dict[str, dict] = {}
    for item in findings:
        entry = merged.get(item["id"])
        if entry is None:
            merged[item["id"]] = {
                "id": item["id"],
                "severity": item["severity"],
                "packages": list(item["packages"]),
                "fix": item["fix"],
            }
            continue
        if _rank(item["severity"]) < _rank(entry["severity"]):
            entry["severity"] = item["severity"]
        for package in item["packages"]:
            if package not in entry["packages"]:
                entry["packages"].append(package)
        if item["fix"] and not entry["fix"]:
            entry["fix"] = item["fix"]
    for entry in merged.values():
        entry["packages"].sort()
    return sorted(merged.values(), key=lambda e: (_rank(e["severity"]), e["id"]))


def _distinct(summaries: list[PlatformSummary]) -> list[dict]:
    return _merge(
        [
            item
            for summary in summaries
            for scanner in (summary.grype, summary.trivy)
            for item in scanner["findings"]
        ]
    )


def _counts(summaries: list[PlatformSummary]) -> tuple[int, int, int]:
    """Distinct vulnerabilities: (fixable High+, unfixed High+, everything).

    On a Debian base, findings Debian has marked won't-fix or not yet fixed
    are the steady state: nothing can be upgraded, so they are recorded but
    not actionable. Only a fix available to move to is.
    """
    distinct = _distinct(summaries)
    high = [e for e in distinct if e["severity"] in ACTIONABLE]
    fixable = sum(1 for e in high if e["fix"])
    return fixable, len(high) - fixable, len(distinct)


def verdict(summaries: list[PlatformSummary]) -> str:
    """One line stating whether anything needs doing.

    Suppressed findings are excluded because they are decisions already
    recorded, not open work.
    """
    actionable, unfixed, everything = _counts(summaries)
    if actionable:
        return (
            f"Action needed: {actionable} High or Critical finding(s) with a "
            "fix available against the current release."
        )
    if unfixed:
        lower = everything - unfixed
        tail = f", and {lower} lower-severity finding(s)" if lower else ""
        return (
            f"No fixable High or Critical findings. {unfixed} High or Critical "
            f"finding(s) have no fix yet{tail}, recorded below."
        )
    if everything:
        return (
            f"No High or Critical findings. {everything} lower-severity "
            "finding(s) recorded below."
        )
    return "No findings."


def scanned_at(summaries: list[PlatformSummary]) -> str:
    return next(
        (
            s.grype.get("scanned") or s.trivy.get("scanned")
            for s in summaries
            if s.grype.get("scanned") or s.trivy.get("scanned")
        ),
        "",
    )


def badge(summaries: list[PlatformSummary]) -> dict:
    """The verdict in the shields.io endpoint schema, for the README badge."""
    actionable, unfixed, everything = _counts(summaries)
    if actionable:
        message, color = f"{actionable} High or Critical, action needed", "red"
    elif unfixed:
        message, color = f"no fixable High or Critical, {unfixed} unfixed", "yellow"
    elif everything:
        message, color = f"no High or Critical, {everything} lower", "brightgreen"
    else:
        message, color = "no findings", "brightgreen"

    checked = scanned_at(summaries)
    label = f"scanned {checked[:10]}" if checked else "security status"
    return {"schemaVersion": 1, "label": label, "message": message, "color": color}


def render_status(
    image: str,
    tag: str,
    index_digest: str,
    summaries: list[PlatformSummary],
) -> str:
    checked = scanned_at(summaries)
    database = next((s.grype.get("db_built") for s in summaries if s.grype.get("db_built")), "")

    out: list[str] = []
    out.append("# Security status")
    out.append("")
    out.append(verdict(summaries))
    out.append("")
    out.append(f"Release `{tag}`, published as `{image}:{tag}` and `{image}:latest`.")
    out.append(f"Manifest list `{index_digest}`.")
    if checked:
        line = f"Re-scanned {checked}"
        if database:
            line += f" against a vulnerability database built {database}"
        out.append(f"{line}.")
    out.append("")
    out.append(
        "This page is regenerated on a schedule from the CycloneDX SBOM "
        "attached to the published image, so it reflects what the scanners "
        "know now rather than what they knew at build time. It is generated "
        "output and is not signed. The per-release pages under Releases are "
        "the build-time snapshots and do not change. Counts are of distinct "
        "vulnerabilities: one reported by both scanners, or on several "
        "platforms, is counted once, at the higher severity either scanner gives."
    )

    for summary in summaries:
        out.append("")
        out.append(f"## {summary.slug}")
        out.append("")
        out.append(f"Image digest: `{summary.digest}`")
        out.append("")

        findings = _merge(summary.grype["findings"] + summary.trivy["findings"])
        if not findings:
            out.append("No findings.")
        else:
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
            out.append(
                "Suppressed by `.grype-ignore.yaml`. A fix version appearing "
                "on a line this image can actually move to retires the "
                "suppression; the reason column names the tracking issue."
            )
            out.append("")
            out.append("| CVE | Severity | Package | Fixed in | Reason |")
            out.append("|---|---|---|---|---|")
            for item in summary.grype["suppressed"]:
                package = item["package"]
                if item["version"]:
                    package = f"{package} {item['version']}"
                fix = cell(item["fix"]) if item["fix"] else "No fix available"
                reason = cell(item["reason"]) if item["reason"] else "No reason recorded"
                out.append(
                    f"| {cell(item['id'])} | {cell(item['severity'])} "
                    f"| {cell(package)} | {fix} | {reason} |"
                )

    out.append("")
    return "\n".join(out)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--index-digest", required=True)
    parser.add_argument("--reports-dir", required=True, type=Path)
    parser.add_argument(
        "--platform", action="append", required=True, metavar="SLUG=DIGEST"
    )
    parser.add_argument("--expect-platforms", type=int)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--badge", type=Path, help="Also write the verdict as a shields.io endpoint JSON file.")
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

    if args.expect_platforms is not None and len(summaries) != args.expect_platforms:
        parser.error(
            f"expected {args.expect_platforms} platforms, rendered "
            f"{len(summaries)}: {[s.slug for s in summaries]}"
        )

    body = render_status(args.image, args.tag, args.index_digest, summaries)
    if args.output:
        args.output.write_text(body)
    else:
        sys.stdout.write(body)
    if args.badge:
        args.badge.write_text(json.dumps(badge(summaries), indent=2) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
