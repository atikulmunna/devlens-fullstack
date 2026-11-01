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
        "removed_checks": [],
        "tests": {"tests_to_run": [], "untested": []},
        "reviewers": [],
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


def test_removed_checks_come_first_with_links_to_the_base_line() -> None:
    body = _render(
        removed_checks=[
            {"path": "app/views.py", "line": 12, "kind": "auth check", "text": "@login_required"},
            {"path": "app/csrf.py", "line": 3, "kind": "CSRF protection", "text": "app.use(csrf({ cookie: true }))"},
        ],
        flags=[{"path": "app/views.py", "categories": ["removed: auth"], "severity": "high"}],
    )
    assert "1 file changed. 2 checks removed, listed first." in body
    assert body.index("#### Removed checks") < body.index("#### Security-sensitive changes")
    assert f"| Auth check | [`app/views.py:12`](https://github.com/{REPO}/blob/{BASE}/app/views.py#L12) |" in body
    assert "| CSRF protection |" in body
    assert "| `@login_required` |" in body


def test_removed_lines_are_shortened_and_cannot_break_the_table() -> None:
    long_line = "if not (user and user.has_perm('x') or 'a|b' in roles): " + "x" * 80
    body = _render(removed_checks=[{"path": "a.py", "line": 1, "kind": "permission check", "text": long_line}])
    row = next(line for line in body.splitlines() if line.startswith("| Permission check"))
    assert "'a\|b'" in row
    assert row.endswith('...` |') and len(row) < 220
    ticks = _render(removed_checks=[{"path": "a.py", "line": 1, "kind": "auth check", "text": "q = `auth`"}])
    assert "| `` q = `auth` `` |" in ticks


def test_tests_to_run_and_untested_files_get_a_section_and_a_sentence() -> None:
    body = _render(tests={"tests_to_run": ["tests/test_a.py", "tests/test_b.py"], "untested": ["app/pay.py"]})
    assert "2 test files exercise them. No test imports 1 of the changed files." in body
    assert "- **To run (2):** `tests/test_a.py`, `tests/test_b.py`" in body
    assert "- **Changed, and no test imports them (1):** `app/pay.py`" in body


def test_counts_of_one_take_a_singular_verb() -> None:
    body = _render(
        flags=[{"path": "a.py", "categories": ["auth"], "severity": "medium"}],
        blast={"impacted_by_depth": [["b.py"]], "impacted_count": 1},
        tests={"tests_to_run": ["tests/test_a.py"], "untested": []},
    )
    assert "1 other file imports them." in body
    assert "1 changed file touches security-sensitive code." in body
    assert "1 test file exercises them." in body


def test_reviewers_are_profile_links_never_mentions() -> None:
    body = _render(
        reviewers=[
            {"name": "Ben", "login": "benb", "files": ["a.py", "b.py"], "commits": 4},
            {"name": "Ana Lima", "login": None, "files": ["a.py"], "commits": 1},
        ]
    )
    assert "#### Suggested reviewers" in body
    assert "- [benb](https://github.com/benb): 2 of the changed files, 4 commits" in body
    assert "- Ana Lima: 1 of the changed files, 1 commit" in body
    assert "@" not in body.split("#### Suggested reviewers")[1]
