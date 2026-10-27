import json
import re
from pathlib import Path

import pytest

from scripts.render_release_report import (
    SEVERITY_ORDER,
    PlatformSummary,
    cell,
    main,
    normalize_timestamp,
    render_report,
    summarize_grype,
    summarize_platform,
    summarize_sbom,
    summarize_trivy,
)

# --- SBOM component counts ----------------------------------------------------


def test_summarize_sbom_counts_by_type():
    doc = {
        "components": [
            {"type": "library", "name": "a", "version": "1"},
            {"type": "library", "name": "b", "version": "2"},
            {"type": "file", "name": "c"},
            {"type": "operating-system", "name": "alpine", "version": "3.24.1"},
        ]
    }
    assert summarize_sbom(doc) == {
        "total": 4,
        "by_type": {"library": 2, "file": 1, "operating-system": 1},
    }


def test_summarize_sbom_handles_absent_components():
    assert summarize_sbom({}) == {"total": 0, "by_type": {}}


# --- Grype: active findings vs suppressed -------------------------------------


def test_summarize_grype_counts_active_by_severity():
    doc = {
        "matches": [
            {
                "vulnerability": {"id": "CVE-1", "severity": "Medium"},
                "artifact": {"name": "python", "version": "3.13.14"},
            },
            {
                "vulnerability": {"id": "CVE-2", "severity": "Medium"},
                "artifact": {"name": "python", "version": "3.13.14"},
            },
            {
                "vulnerability": {"id": "CVE-3", "severity": "Low"},
                "artifact": {"name": "busybox", "version": "1.37"},
            },
        ]
    }
    result = summarize_grype(doc)
    assert result["by_severity"] == {"Medium": 2, "Low": 1}
    assert result["suppressed"] == []
    assert [f["id"] for f in result["findings"]] == ["CVE-1", "CVE-2", "CVE-3"]


def test_summarize_grype_groups_one_cve_across_packages():
    """One CVE hitting three packages is one row naming all three, not three
    rows that read as three problems."""
    doc = {
        "matches": [
            {
                "vulnerability": {"id": "CVE-9", "severity": "Medium"},
                "artifact": {"name": "busybox", "version": "1.37.0-r31"},
            },
            {
                "vulnerability": {"id": "CVE-9", "severity": "Medium"},
                "artifact": {"name": "ssl_client", "version": "1.37.0-r31"},
            },
        ]
    }
    result = summarize_grype(doc)
    assert result["by_severity"] == {"Medium": 2}
    assert result["findings"] == [
        {
            "id": "CVE-9",
            "severity": "Medium",
            "packages": ["busybox 1.37.0-r31", "ssl_client 1.37.0-r31"],
            "fix": "",
        }
    ]


def test_summarize_grype_records_the_fix_version():
    doc = {
        "matches": [
            {
                "vulnerability": {
                    "id": "CVE-1",
                    "severity": "Medium",
                    "fix": {"state": "fixed", "versions": ["3.15.0a6"]},
                },
                "artifact": {"name": "python", "version": "3.13.14"},
            }
        ]
    }
    assert summarize_grype(doc)["findings"][0]["fix"] == "3.15.0a6"


def test_summarize_grype_orders_findings_most_severe_first():
    doc = {
        "matches": [
            {
                "vulnerability": {"id": "CVE-LOW", "severity": "Low"},
                "artifact": {"name": "a", "version": "1"},
            },
            {
                "vulnerability": {"id": "CVE-HIGH", "severity": "High"},
                "artifact": {"name": "b", "version": "1"},
            },
        ]
    }
    assert [f["id"] for f in summarize_grype(doc)["findings"]] == [
        "CVE-HIGH",
        "CVE-LOW",
    ]


def test_summarize_grype_lists_suppressed_separately():
    """A suppressed finding must stay visible. Counting it as active would
    misreport the gate, and dropping it hides what a rule chose to allow."""
    doc = {
        "matches": [],
        "ignoredMatches": [
            {
                "vulnerability": {"id": "CVE-2026-11940", "severity": "High"},
                "artifact": {"name": "python", "version": "3.13.14"},
                "appliedIgnoreRules": [
                    {
                        "vulnerability": "CVE-2026-11940",
                        "reason": "unreachable. Tracked in #5",
                    }
                ],
            }
        ],
    }
    result = summarize_grype(doc)
    assert result["by_severity"] == {}
    assert result["suppressed"] == [
        {
            "id": "CVE-2026-11940",
            "severity": "High",
            "package": "python",
            "version": "3.13.14",
            "rules": ["CVE-2026-11940"],
            "reason": "unreachable. Tracked in #5",
            "fix": "",
        }
    ]


def test_summarize_grype_reports_a_suppression_with_no_stated_reason():
    """A rule without a reason is worth seeing as such rather than rendering
    an empty cell that reads like a formatting bug."""
    doc = {
        "ignoredMatches": [
            {
                "vulnerability": {"id": "CVE-1", "severity": "High"},
                "artifact": {"name": "python", "version": "3.13.14"},
                "appliedIgnoreRules": [{"vulnerability": "CVE-1"}],
            }
        ]
    }
    assert summarize_grype(doc)["suppressed"][0]["reason"] == ""


def test_summarize_grype_handles_absent_keys():
    assert summarize_grype({}) == {
        "by_severity": {},
        "fixable_by_severity": {},
        "suppressed": [],
        "findings": [],
        "scanned": "",
        "db_built": "",
    }


# --- Trivy --------------------------------------------------------------------


def test_summarize_trivy_counts_by_severity():
    doc = {
        "Results": [
            {
                "Target": "os-pkgs",
                "Vulnerabilities": [
                    {
                        "VulnerabilityID": "CVE-1",
                        "Severity": "HIGH",
                        "PkgName": "openssl",
                        "InstalledVersion": "3.0.0",
                        "FixedVersion": "3.0.1",
                    },
                    {
                        "VulnerabilityID": "CVE-2",
                        "Severity": "LOW",
                        "PkgName": "busybox",
                        "InstalledVersion": "1.37",
                    },
                ],
            }
        ]
    }
    result = summarize_trivy(doc)
    assert result["by_severity"] == {"High": 1, "Low": 1}
    assert result["findings"] == [
        {
            "id": "CVE-1",
            "severity": "High",
            "packages": ["openssl 3.0.0"],
            "fix": "3.0.1",
        },
        {"id": "CVE-2", "severity": "Low", "packages": ["busybox 1.37"], "fix": ""},
    ]


def test_summarize_trivy_handles_clean_result_omitting_vulnerabilities():
    """Trivy drops the Vulnerabilities key entirely on a clean target rather
    than emitting an empty list."""
    doc = {"Results": [{"Target": "os-pkgs", "Class": "os-pkgs"}]}
    assert summarize_trivy(doc) == {
        "by_severity": {},
        "fixable_by_severity": {},
        "findings": [],
        "scanned": "",
    }


def test_summarize_trivy_handles_absent_results():
    assert summarize_trivy({}) == {
        "by_severity": {},
        "fixable_by_severity": {},
        "findings": [],
        "scanned": "",
    }


# --- Timestamps: the staleness signal -----------------------------------------


def test_normalize_timestamp_accepts_trivy_nanoseconds():
    """Trivy emits nine fractional digits, which datetime.fromisoformat
    rejects on 3.11. Normalize before parsing rather than at the caller."""
    assert normalize_timestamp("2026-08-05T09:41:10.957082907Z") == "2026-08-05 09:41 UTC"


def test_normalize_timestamp_converts_a_local_offset_to_utc():
    assert normalize_timestamp("2026-08-05T06:28:49.467313-04:00") == "2026-08-05 10:28 UTC"


def test_normalize_timestamp_passes_through_unparseable_input():
    """A scanner changing its format must not lose the whole report."""
    assert normalize_timestamp("not a date") == "not a date"
    assert normalize_timestamp("") == ""


def test_summarize_grype_reports_when_it_scanned_and_its_database_age():
    """v0.116 nests the database date under db.status, which is the shape the
    committed fixture carries."""
    doc = {
        "descriptor": {
            "timestamp": "2026-08-05T06:28:49.467313-04:00",
            "db": {"status": {"built": "2026-08-05T07:04:14Z"}},
        }
    }
    result = summarize_grype(doc)
    assert result["scanned"] == "2026-08-05 10:28 UTC"
    assert result["db_built"] == "2026-08-05 07:04 UTC"


def test_summarize_grype_reads_the_flat_database_date_from_older_grype():
    doc = {"descriptor": {"db": {"built": "2026-08-05T07:04:14Z"}}}
    assert summarize_grype(doc)["db_built"] == "2026-08-05 07:04 UTC"


def test_summarize_platform_finds_the_database_date_in_the_real_fixture(report_dir):
    """Guards against asserting a shape no scanner actually emits."""
    grype = json.loads((report_dir / "grype-report.linux-amd64.json").read_text())
    assert summarize_grype(grype)["db_built"].endswith("UTC")


def test_summarize_trivy_reports_when_it_scanned():
    assert summarize_trivy({"CreatedAt": "2026-08-05T09:41:10.957082907Z"})[
        "scanned"
    ] == "2026-08-05 09:41 UTC"


def test_render_report_dates_the_scan():
    """A page with no date reads as current forever. The findings are a
    snapshot and have to say when."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [_summary(grype={**_summary().grype, "scanned": "2026-08-05 10:28 UTC"})],
    )
    assert "2026-08-05 10:28 UTC" in out


def test_render_report_says_findings_are_a_snapshot():
    out = render_report("v1.0.0-4", "sha256:index", [_summary()])
    assert "snapshot" in out.lower()


# --- Escaping scanner-supplied text -------------------------------------------


def test_cell_escapes_a_pipe_so_it_cannot_break_the_row():
    assert "\\|" in cell("evil | name")


def test_cell_neutralizes_markup():
    assert "<img" not in cell("<img src=x onerror=alert(1)>")


def test_cell_strips_control_characters():
    """Removing ESC leaves the sequence as ordinary text rather than letting
    a terminal act on it."""
    assert cell("a\x1b[31mb\x00c") == "a[31mbc"


def test_cell_flattens_newlines():
    assert "\n" not in cell("line one\nline two")


def test_render_report_does_not_let_a_package_name_break_the_table():
    """SBOM text describes whatever is installed in the image, so it is
    untrusted the same way a catalog-supplied filename is."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary(
                grype={
                    "by_severity": {"High": 1},
                    "suppressed": [],
                    "scanned": "",
                    "db_built": "",
                    "findings": [
                        {
                            "id": "CVE-1",
                            "severity": "High",
                            "packages": ["evil | <img src=x onerror=alert(1)>"],
                            "fix": "",
                        }
                    ],
                }
            )
        ],
    )
    row = next(line for line in out.splitlines() if "CVE-1" in line)
    assert len(re.findall(r"(?<!\\)\|", row)) == 5
    assert "\\|" in row
    assert "<img" not in row


# --- Platform count guard -----------------------------------------------------


def test_main_refuses_when_a_platform_is_missing(report_dir, tmp_path):
    """reports-* uploads with if-no-files-found: warn, so a lost architecture
    reaches this script as a shorter list rather than an error."""
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--tag",
                "v1.0.0-4",
                "--index-digest",
                "sha256:index",
                "--reports-dir",
                str(report_dir),
                "--platform",
                "linux-amd64=sha256:amd",
                "--expect-platforms",
                "2",
                "--output",
                str(tmp_path / "body.md"),
            ]
        )
    assert excinfo.value.code != 0


def test_main_accepts_a_matching_platform_count(report_dir, tmp_path):
    out = tmp_path / "body.md"
    assert (
        main(
            [
                "--tag",
                "v1.0.0-4",
                "--index-digest",
                "sha256:index",
                "--reports-dir",
                str(report_dir),
                "--platform",
                "linux-amd64=sha256:amd",
                "--expect-platforms",
                "1",
                "--output",
                str(out),
            ]
        )
        == 0
    )
    assert out.read_text()


# --- Severity ordering --------------------------------------------------------


def test_severity_order_is_most_severe_first():
    assert SEVERITY_ORDER.index("Critical") < SEVERITY_ORDER.index("High")
    assert SEVERITY_ORDER.index("High") < SEVERITY_ORDER.index("Medium")
    assert SEVERITY_ORDER.index("Medium") < SEVERITY_ORDER.index("Low")


# --- Rendering ----------------------------------------------------------------


def _summary(slug="linux-amd64", digest="sha256:aaa", **overrides):
    defaults = {
        "slug": slug,
        "digest": digest,
        "sbom": {"total": 3, "by_type": {"library": 2, "file": 1}},
        "grype": {
            "by_severity": {"Medium": 1},
            "suppressed": [],
            "findings": [
                {
                    "id": "CVE-1",
                    "severity": "Medium",
                    "packages": ["python 3.13.14"],
                    "fix": "",
                }
            ],
        },
        "trivy": {"by_severity": {}, "findings": []},
    }
    defaults.update(overrides)
    return PlatformSummary(**defaults)


def test_render_report_names_the_tag_and_index_digest():
    out = render_report("v1.0.0-4", "sha256:index", [_summary()])
    assert "v1.0.0-4" in out
    assert "sha256:index" in out


def test_render_report_includes_each_platform_digest():
    """The digest is what a reader verifies against, so it has to be in the
    document rather than only in the workflow log."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary("linux-amd64", "sha256:amd"),
            _summary("linux-arm64", "sha256:arm"),
        ],
    )
    assert "linux-amd64" in out
    assert "sha256:amd" in out
    assert "linux-arm64" in out
    assert "sha256:arm" in out


def test_render_report_states_no_findings_explicitly():
    """An empty table reads as a missing scan. Say the scan ran and was
    clean."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [_summary(grype={"by_severity": {}, "suppressed": [], "findings": []})],
    )
    assert "No findings" in out


def test_render_report_lists_every_active_cve():
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary(
                grype={
                    "by_severity": {"Medium": 1, "Low": 1},
                    "suppressed": [],
                    "findings": [
                        {
                            "id": "CVE-2026-0864",
                            "severity": "Medium",
                            "packages": ["python 3.13.14"],
                            "fix": "3.15.0b4",
                        },
                        {
                            "id": "CVE-2026-6879",
                            "severity": "Low",
                            "packages": ["python 3.13.14"],
                            "fix": "",
                        },
                    ],
                }
            )
        ],
    )
    assert "CVE-2026-0864" in out
    assert "CVE-2026-6879" in out
    assert "3.15.0b4" in out


def test_render_report_marks_an_unfixed_finding():
    """An empty fix cell is ambiguous. Say there is no fix."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary(
                grype={
                    "by_severity": {"Medium": 1},
                    "suppressed": [],
                    "findings": [
                        {
                            "id": "CVE-1",
                            "severity": "Medium",
                            "packages": ["busybox 1.37"],
                            "fix": "",
                        }
                    ],
                }
            )
        ],
    )
    assert "No fix" in out


def test_render_report_shows_the_suppression_reason():
    """The reason carries the issue that tracks the suppression, so it has to
    reach the page rather than staying in the ignore file."""
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary(
                grype={
                    "by_severity": {},
                    "findings": [],
                    "suppressed": [
                        {
                            "id": "CVE-2026-11940",
                            "severity": "High",
                            "package": "python",
                            "version": "3.13.14",
                            "rules": ["CVE-2026-11940"],
                            "reason": "unreachable. Tracked in #5, retired by #7",
                        }
                    ],
                }
            )
        ],
    )
    assert "Tracked in #5" in out
    assert "retired by #7" in out


def test_render_report_shows_suppressed_with_severity():
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [
            _summary(
                grype={
                    "by_severity": {},
                    "findings": [],
                    "suppressed": [
                        {
                            "id": "CVE-2026-11940",
                            "severity": "High",
                            "package": "python",
                            "version": "3.13.14",
                            "rules": ["CVE-2026-11940"],
                            "reason": "",
                        }
                    ],
                }
            )
        ],
    )
    assert "CVE-2026-11940" in out
    assert "High" in out
    assert "python" in out


def test_render_report_orders_severities_most_severe_first():
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [_summary(grype={"by_severity": {"Low": 1, "High": 2}, "suppressed": [], "findings": []})],
    )
    assert out.index("High") < out.index("Low")


# --- End to end against the committed fixtures --------------------------------


@pytest.fixture
def report_dir():
    return Path(__file__).parent / "fixtures" / "reports"


def test_summarize_platform_reads_a_real_report_set(report_dir):
    summary = summarize_platform(
        slug="linux-amd64",
        digest="sha256:6441a5df9615",
        sbom=json.loads((report_dir / "sbom.cyclonedx.linux-amd64.json").read_text()),
        grype=json.loads((report_dir / "grype-report.linux-amd64.json").read_text()),
        trivy=json.loads((report_dir / "trivy-report.linux-amd64.json").read_text()),
    )
    assert summary.slug == "linux-amd64"
    assert summary.sbom["total"] > 0
    assert summary.grype["by_severity"]
    assert len(summary.grype["suppressed"]) == 3
    # Every suppression in the committed ignore file names its tracking issue.
    assert all("#5" in s["reason"] for s in summary.grype["suppressed"])
    # One busybox CVE hits three packages and must collapse to one entry.
    shared = [f for f in summary.grype["findings"] if len(f["packages"]) > 1]
    assert shared and len(shared[0]["packages"]) == 3


def test_render_report_sorts_unknown_severities_after_known_ones():
    out = render_report(
        "v1.0.0-4",
        "sha256:index",
        [_summary(grype={"by_severity": {"Sideways": 1, "Low": 2}, "suppressed": [], "findings": []})],
    )
    assert out.index("2 Low") < out.index("1 Sideways")


# --- The command line CI actually invokes -------------------------------------


def test_main_writes_a_report_for_the_named_platform(report_dir, tmp_path):
    out = tmp_path / "body.md"
    rc = main(
        [
            "--tag",
            "v1.0.0-4",
            "--index-digest",
            "sha256:index",
            "--reports-dir",
            str(report_dir),
            "--platform",
            "linux-amd64=sha256:amd",
            "--output",
            str(out),
        ]
    )
    assert rc == 0
    body = out.read_text()
    assert "v1.0.0-4" in body
    assert "sha256:amd" in body
    assert "CVE-2026-11940" in body


def test_main_rejects_a_platform_without_a_digest(report_dir, tmp_path):
    """A malformed --platform must stop the step rather than publish a report
    that silently omits an architecture."""
    with pytest.raises(SystemExit) as excinfo:
        main(
            [
                "--tag",
                "v1.0.0-4",
                "--index-digest",
                "sha256:index",
                "--reports-dir",
                str(report_dir),
                "--platform",
                "linux-amd64",
                "--output",
                str(tmp_path / "body.md"),
            ]
        )
    assert excinfo.value.code != 0


def test_main_fails_when_a_report_is_missing(tmp_path):
    """A missing report is a broken upload, not an empty scan."""
    with pytest.raises(FileNotFoundError):
        main(
            [
                "--tag",
                "v1.0.0-4",
                "--index-digest",
                "sha256:index",
                "--reports-dir",
                str(tmp_path),
                "--platform",
                "linux-amd64=sha256:amd",
            ]
        )


def test_main_writes_to_stdout_without_output(report_dir, capsys):
    rc = main(
        [
            "--tag",
            "v1.0.0-4",
            "--index-digest",
            "sha256:index",
            "--reports-dir",
            str(report_dir),
            "--platform",
            "linux-amd64=sha256:amd",
        ]
    )
    assert rc == 0
    assert "v1.0.0-4" in capsys.readouterr().out


def test_render_report_on_a_real_report_set_is_markdown(report_dir):
    summary = summarize_platform(
        slug="linux-amd64",
        digest="sha256:6441a5df9615",
        sbom=json.loads((report_dir / "sbom.cyclonedx.linux-amd64.json").read_text()),
        grype=json.loads((report_dir / "grype-report.linux-amd64.json").read_text()),
        trivy=json.loads((report_dir / "trivy-report.linux-amd64.json").read_text()),
    )
    out = render_report("v1.0.0-4", "sha256:index", [summary])
    assert out.startswith("#")
    assert "| " in out
    assert "CVE-2026-11940" in out


# --- Fixability: what a gate on "fixable only" counts --------------------------


def test_summarize_grype_counts_fixable_findings_separately():
    """A finding is fixable when Grype lists a fix version. Debian's won't-fix
    and not-yet-fixed findings have none, and must not count as fixable."""
    doc = {
        "matches": [
            {
                "vulnerability": {"id": "CVE-1", "severity": "High", "fix": {"versions": ["1.2"], "state": "fixed"}},
                "artifact": {"name": "a", "version": "1.0"},
            },
            {
                "vulnerability": {"id": "CVE-2", "severity": "High", "fix": {"versions": [], "state": "wont-fix"}},
                "artifact": {"name": "b", "version": "1.0"},
            },
            {
                "vulnerability": {"id": "CVE-3", "severity": "Critical", "fix": {"state": "not-fixed"}},
                "artifact": {"name": "c", "version": "1.0"},
            },
        ]
    }
    result = summarize_grype(doc)
    assert result["by_severity"] == {"High": 2, "Critical": 1}
    assert result["fixable_by_severity"] == {"High": 1}


def test_summarize_trivy_counts_fixable_findings_separately():
    """Trivy marks a fix with FixedVersion; status 'affected' or
    'will_not_fix' leaves it empty."""
    doc = {
        "Results": [
            {
                "Vulnerabilities": [
                    {"VulnerabilityID": "CVE-1", "Severity": "HIGH", "PkgName": "a", "FixedVersion": "1.2", "Status": "fixed"},
                    {"VulnerabilityID": "CVE-2", "Severity": "CRITICAL", "PkgName": "b", "Status": "affected"},
                    {"VulnerabilityID": "CVE-3", "Severity": "HIGH", "PkgName": "c", "FixedVersion": "", "Status": "will_not_fix"},
                ]
            }
        ]
    }
    result = summarize_trivy(doc)
    assert result["by_severity"] == {"High": 2, "Critical": 1}
    assert result["fixable_by_severity"] == {"High": 1}
