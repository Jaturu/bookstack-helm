import json
from pathlib import Path

import pytest

from scripts.render_release_report import PlatformSummary, summarize_platform
from scripts.rescan_status import badge, main, render_status, verdict

# --- The verdict: the one line someone reads before deciding to run it --------


def _summary(slug="linux-amd64", **overrides):
    defaults = {
        "slug": slug,
        "digest": "sha256:aaa",
        "sbom": {"total": 3, "by_type": {"library": 3}},
        "grype": {
            "by_severity": {},
            "suppressed": [],
            "findings": [],
            "scanned": "2026-08-05 10:28 UTC",
            "db_built": "2026-08-05 07:04 UTC",
        },
        "trivy": {"by_severity": {}, "findings": [], "scanned": ""},
    }
    defaults.update(overrides)
    return PlatformSummary(**defaults)


def _findings(by_severity, fixable=None, prefix="CVE-G"):
    """Synthesize grouped findings matching the counts.

    Every finding has a fix unless ``fixable`` says how many per severity do.
    IDs depend only on prefix, severity and position, so two calls with the
    same prefix describe the same vulnerabilities.
    """
    out = []
    for severity, count in by_severity.items():
        with_fix = count if fixable is None else fixable.get(severity, 0)
        for i in range(count):
            out.append(
                {
                    "id": f"{prefix}-{severity}-{i}",
                    "severity": severity,
                    "packages": [f"pkg-{severity.lower()}-{i} 1.0"],
                    "fix": "1.1" if i < with_fix else "",
                }
            )
    return out


def _finding(vuln_id, severity, fix="", package="pkg 1.0"):
    return {"id": vuln_id, "severity": severity, "packages": [package], "fix": fix}


def _trivy(by_severity=None, fixable=None, findings=None, prefix="CVE-T"):
    by_severity = by_severity or {}
    return {
        "by_severity": by_severity,
        "findings": findings if findings is not None else _findings(by_severity, fixable, prefix),
        "scanned": "",
    }


def _grype(by_severity, findings=None, suppressed=None, fixable=None, prefix="CVE-G"):
    return {
        "by_severity": by_severity,
        "findings": findings if findings is not None else _findings(by_severity, fixable, prefix),
        "suppressed": suppressed or [],
        "scanned": "2026-08-05 10:28 UTC",
        "db_built": "2026-08-05 07:04 UTC",
    }


def test_verdict_is_clean_when_nothing_is_found():
    assert verdict([_summary()]) == "No findings."


def test_verdict_separates_low_severity_from_actionable():
    """Medium findings with no fix are the steady state here. Calling that
    'action needed' would train the reader to ignore the line."""
    out = verdict([_summary(grype=_grype({"Medium": 8, "Low": 1}))])
    assert "No High or Critical" in out
    assert "9" in out


def test_verdict_calls_out_high_severity():
    out = verdict([_summary(grype=_grype({"High": 2, "Medium": 1}))])
    assert out.startswith("Action needed")
    assert "2" in out


def test_verdict_counts_critical_as_actionable():
    assert verdict([_summary(grype=_grype({"Critical": 1}))]).startswith("Action needed")


def test_verdict_totals_distinct_vulnerabilities_across_platforms():
    out = verdict(
        [
            _summary("linux-amd64", grype=_grype({"High": 1}, prefix="CVE-A")),
            _summary("linux-arm64", grype=_grype({"High": 1}, prefix="CVE-B")),
        ]
    )
    assert out.startswith("Action needed: 2 ")


def test_verdict_includes_trivy_findings():
    """Either scanner finding something high is enough to act on."""
    summary = _summary(trivy=_trivy({"High": 1}))
    assert verdict([summary]).startswith("Action needed")


def test_verdict_ignores_suppressed_findings():
    """A suppression is a decision already taken. Counting it as actionable
    would make the page permanently red."""
    suppressed = [
        {
            "id": "CVE-1",
            "severity": "High",
            "package": "python",
            "version": "3.13.14",
            "rules": ["CVE-1"],
            "reason": "unreachable. Tracked in #5",
            "fix": "3.15.0",
        }
    ]
    assert verdict([_summary(grype=_grype({}, suppressed=suppressed))]) == "No findings."


# --- Rendering ----------------------------------------------------------------


def test_render_status_names_the_release_and_when_it_was_checked():
    out = render_status(
        image="docker.io/jaturu/omada-release-watch",
        tag="v1.0.0-4",
        index_digest="sha256:index",
        summaries=[_summary()],
    )
    assert "v1.0.0-4" in out
    assert "docker.io/jaturu/omada-release-watch" in out
    assert "2026-08-05 10:28 UTC" in out
    assert "sha256:index" in out


def test_render_status_leads_with_the_verdict():
    out = render_status(
        image="img", tag="v1", index_digest="sha256:i",
        summaries=[_summary(grype=_grype({"High": 1}))],
    )
    head = "\n".join(out.splitlines()[:8])
    assert "Action needed" in head


def test_render_status_says_it_is_generated_and_not_signed():
    out = render_status(
        image="img", tag="v1", index_digest="sha256:i", summaries=[_summary()]
    )
    assert "not signed" in out


def test_render_status_shows_a_fix_becoming_available_for_a_suppression():
    """The reason a suppression is allowed is that no fix exists on our line.
    When one appears the page has to show it, which is what #5 asks for."""
    suppressed = [
        {
            "id": "CVE-2026-15308",
            "severity": "High",
            "package": "python",
            "version": "3.13.14",
            "rules": ["CVE-2026-15308"],
            "reason": "no 3.13 backport available. Tracked in #5",
            "fix": "3.13.15",
        }
    ]
    out = render_status(
        image="img", tag="v1", index_digest="sha256:i",
        summaries=[_summary(grype=_grype({}, suppressed=suppressed))],
    )
    assert "3.13.15" in out
    assert "CVE-2026-15308" in out


def test_render_status_escapes_scanner_text():
    out = render_status(
        image="img", tag="v1", index_digest="sha256:i",
        summaries=[
            _summary(
                grype=_grype(
                    {"High": 1},
                    findings=[
                        {
                            "id": "CVE-1",
                            "severity": "High",
                            "packages": ["evil | <img src=x>"],
                            "fix": "",
                        }
                    ],
                )
            )
        ],
    )
    assert "<img" not in out


def test_render_status_is_stable_for_identical_input():
    """The workflow commits only when the file changes, so equal scans must
    produce byte-identical output or it would commit every day."""
    args = dict(
        image="img", tag="v1", index_digest="sha256:i", summaries=[_summary()]
    )
    assert render_status(**args) == render_status(**args)


# --- End to end against a real re-scan ----------------------------------------


@pytest.fixture
def report_dir():
    return Path(__file__).parent / "fixtures" / "reports"


def test_main_renders_from_real_reports(report_dir, tmp_path):
    out = tmp_path / "status.md"
    rc = main(
        [
            "--image", "docker.io/jaturu/omada-release-watch",
            "--tag", "v1.0.0-4",
            "--index-digest", "sha256:index",
            "--reports-dir", str(report_dir),
            "--platform", "linux-amd64=sha256:amd",
            "--expect-platforms", "1",
            "--output", str(out),
        ]
    )
    assert rc == 0
    body = out.read_text()
    assert "No High or Critical" in body
    assert "CVE-2026-11940" in body


def test_main_refuses_a_missing_platform(report_dir, tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--image", "img",
                "--tag", "v1",
                "--index-digest", "sha256:i",
                "--reports-dir", str(report_dir),
                "--platform", "linux-amd64=sha256:amd",
                "--expect-platforms", "2",
                "--output", str(tmp_path / "s.md"),
            ]
        )
    assert excinfo.value.code != 0


def test_summarize_platform_still_reads_the_fixture(report_dir):
    summary = summarize_platform(
        slug="linux-amd64",
        digest="sha256:amd",
        sbom=json.loads((report_dir / "sbom.cyclonedx.linux-amd64.json").read_text()),
        grype=json.loads((report_dir / "grype-report.linux-amd64.json").read_text()),
        trivy=json.loads((report_dir / "trivy-report.linux-amd64.json").read_text()),
    )
    # Every suppression carries a fix version today, all on the 3.15 line.
    assert all(s["fix"] for s in summary.grype["suppressed"])


# --- The badge: the verdict as a shields.io endpoint for the README ------------


def test_badge_is_green_and_dated_when_nothing_is_found():
    out = badge([_summary()])
    assert out == {
        "schemaVersion": 1,
        "label": "scanned 2026-08-05",
        "message": "no findings",
        "color": "brightgreen",
    }


def test_badge_counts_lower_severity_findings_in_green():
    out = badge([_summary(grype=_grype({"Medium": 8, "Low": 1}))])
    assert out["message"] == "no High or Critical, 9 lower"
    assert out["color"] == "brightgreen"


def test_badge_turns_red_on_an_actionable_finding():
    out = badge([_summary(grype=_grype({"High": 2, "Medium": 1}))])
    assert out["message"] == "2 High or Critical, action needed"
    assert out["color"] == "red"


def test_badge_falls_back_to_a_plain_label_without_a_scan_date():
    grype = _grype({})
    grype["scanned"] = ""
    assert badge([_summary(grype=grype)])["label"] == "security status"


def test_main_writes_the_badge_beside_the_page(report_dir, tmp_path):
    out = tmp_path / "status.md"
    badge_path = tmp_path / "status.json"
    rc = main(
        [
            "--image", "docker.io/jaturu/omada-release-watch",
            "--tag", "v1.0.0-4",
            "--index-digest", "sha256:index",
            "--reports-dir", str(report_dir),
            "--platform", "linux-amd64=sha256:amd",
            "--expect-platforms", "1",
            "--output", str(out),
            "--badge", str(badge_path),
        ]
    )
    assert rc == 0
    data = json.loads(badge_path.read_text())
    assert data["schemaVersion"] == 1
    assert data["message"].startswith("no High or Critical")
    assert data["color"] == "brightgreen"


# --- Fixability: unfixed findings are recorded, not actionable ---------------
#
# On a Debian base, High and Critical findings that Debian has marked won't-fix
# or not yet fixed are the steady state: there is nothing to upgrade to. Only a
# finding with a fix available is something to act on.


def _fixable(by_severity, fixable):
    return _grype(by_severity, fixable=fixable)


def test_verdict_does_not_act_on_unfixed_high_findings():
    out = verdict([_summary(grype=_fixable({"High": 3, "Critical": 1, "Medium": 2}, {}))])
    assert not out.startswith("Action needed")
    assert out.startswith("No fixable High or Critical findings.")
    assert "4 High or Critical" in out
    assert "no fix yet" in out
    assert "2 lower-severity" in out


def test_verdict_acts_on_a_fixable_high_finding_only():
    out = verdict([_summary(grype=_fixable({"High": 3}, {"High": 1}))])
    assert out.startswith("Action needed: 1 High or Critical finding(s) with a fix available")


def test_verdict_counts_fixable_trivy_findings():
    summary = _summary(trivy=_trivy({"Critical": 2}, {"Critical": 1}))
    assert verdict([summary]).startswith("Action needed: 1 ")


def test_badge_is_yellow_for_unfixed_high_findings():
    out = badge([_summary(grype=_fixable({"High": 3, "Low": 1}, {}))])
    assert out["message"] == "no fixable High or Critical, 3 unfixed"
    assert out["color"] == "yellow"


def test_badge_turns_red_only_for_fixable_findings():
    out = badge([_summary(grype=_fixable({"High": 3}, {"High": 2}))])
    assert out["message"] == "2 High or Critical, action needed"
    assert out["color"] == "red"


# --- Counting: each vulnerability once ---------------------------------------
#
# Two scanners on two platforms report most CVEs four times. The verdict and
# badge count each vulnerability ID once, so the number means something.


def test_same_cve_from_both_scanners_counts_once():
    summary = _summary(
        grype=_grype({}, findings=[_finding("CVE-1", "High")]),
        trivy=_trivy(findings=[_finding("CVE-1", "High")]),
    )
    out = verdict([summary])
    assert "1 High or Critical" in out


def test_same_cve_on_every_platform_counts_once():
    def one():
        return _summary(
            grype=_grype({}, findings=[_finding("CVE-1", "High")]),
            trivy=_trivy(findings=[_finding("CVE-1", "High")]),
        )

    summaries = [one(), one()]
    summaries[1].slug = "linux-arm64"
    assert badge(summaries)["message"] == "no fixable High or Critical, 1 unfixed"


def test_scanners_disagreeing_on_severity_take_the_higher():
    summary = _summary(
        grype=_grype({}, findings=[_finding("CVE-1", "Medium")]),
        trivy=_trivy(findings=[_finding("CVE-1", "High")]),
    )
    assert badge([summary])["message"] == "no fixable High or Critical, 1 unfixed"


def test_a_fix_from_either_scanner_makes_it_fixable():
    """If either scanner knows a fix, its gate will fail on it, so the page
    has to call it actionable too."""
    summary = _summary(
        grype=_grype({}, findings=[_finding("CVE-1", "High")]),
        trivy=_trivy(findings=[_finding("CVE-1", "High", fix="1.2")]),
    )
    assert verdict([summary]).startswith("Action needed: 1 ")


def test_lower_severity_count_is_distinct_too():
    summary = _summary(
        grype=_grype({}, findings=[_finding("CVE-1", "Medium"), _finding("CVE-2", "Low")]),
        trivy=_trivy(findings=[_finding("CVE-1", "Medium")]),
    )
    assert badge([summary])["message"] == "no High or Critical, 2 lower"


def test_platform_table_lists_each_cve_once():
    summary = _summary(
        grype=_grype({}, findings=[_finding("CVE-1", "Medium", package="libfoo 1.0")]),
        trivy=_trivy(findings=[_finding("CVE-1", "High", package="libfoo 1.0")]),
    )
    out = render_status(image="img", tag="v1", index_digest="sha256:i", summaries=[summary])
    rows = [line for line in out.splitlines() if line.startswith("| CVE-1 ")]
    assert rows == ["| CVE-1 | High | libfoo 1.0 | No fix available |"]
