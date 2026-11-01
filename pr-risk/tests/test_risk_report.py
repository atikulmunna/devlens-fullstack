from risk_report import MARKER, MAX_LISTED, render_report

REPO = "acme/shop"
BASE = "b" * 40
HEAD = "a" * 40


def _render(**overrides) -> str:
    args = {
        "repo": REPO,
        "base_sha": BASE,
        "head_sha": HEAD,
        "changed_files": [{"path": "app/auth.py", "status": "modified"}],
        "flags": [],
        "blast": {"impacted_by_depth": [], "impacted_count": 0},
        "still_imported": {},
    }
    return render_report(**{**args, **overrides})


def test_report_starts_with_the_marker_and_says_when_nothing_is_at_risk() -> None:
    body = _render()
    assert body.startswith(MARKER + "\n### DevLens change risk")
    assert "1 file changed. Nothing else imports them, and none touch security-sensitive code." in body
    assert "####" not in body


def test_summary_counts_reach_and_high_severity() -> None:
    body = _render(
        changed_files=[{"path": "a.py", "status": "modified"}, {"path": "b.py", "status": "added"}],
        flags=[
            {"path": "a.py", "categories": ["secret"], "severity": "high"},
            {"path": "b.py", "categories": ["auth"], "severity": "medium"},
        ],
        blast={"impacted_by_depth": [["c.py", "d.py"], ["e.py"]], "impacted_count": 3},
    )
    assert (
        "2 files changed. 3 other files import them, up to 2 imports away. "
        "2 changed files touch security-sensitive code, 1 of them high." in body
    )


def test_security_rows_are_ordered_by_severity_and_link_to_the_head() -> None:
    body = _render(
        flags=[
            {"path": "z/low.py", "categories": ["env"], "severity": "low"},
            {"path": "m/medium.py", "categories": ["auth"], "severity": "medium"},
            {"path": "a/high file.py", "categories": ["auth", "removed: token"], "severity": "high"},
        ]
    )
    rows = [
        line for line in body.splitlines() if line.startswith("| ") and not line.startswith(("| Severity", "| ---"))
    ]
    assert [row.split(" | ")[0] for row in rows] == ["| **High**", "| Medium", "| Low"]
    assert f"(https://github.com/{REPO}/blob/{HEAD}/a/high%20file.py)" in rows[0]
    assert rows[0].endswith("| auth, removed: token |")


def test_long_import_lists_are_cut_with_a_count() -> None:
    level = [f"mod{n:02}.py" for n in range(MAX_LISTED + 4)]
    body = _render(blast={"impacted_by_depth": [level, ["deep.py"]], "impacted_count": len(level) + 1})
    assert f"- **Directly ({len(level)}):**" in body
    assert "`mod14.py`, and 4 more" in body
    assert "`mod15.py`" not in body
    assert "- **2 imports away (1):** `deep.py`" in body


def test_deleted_files_that_are_still_imported_link_to_the_base() -> None:
    body = _render(still_imported={"app/old.py": ["app/b.py", "app/a.py"]})
    assert "#### Deleted but still imported" in body
    assert f"[`app/old.py`](https://github.com/{REPO}/blob/{BASE}/app/old.py) is deleted, but" in body
    assert "`app/a.py`, `app/b.py` still import it." in body


def test_footer_names_the_head_and_links_to_devlens_only_when_configured() -> None:
    assert "<sub>From the Python and JavaScript/TypeScript import graph at aaaaaaa.</sub>" in _render()
    linked = _render(devlens_url="https://devlens.example/")
    assert "[Open in DevLens](https://devlens.example/r/acme/shop/changes)" in linked
