from reviewers import noreply_login, parse_log, suggest_reviewers

US, RS = "\x1f", "\x1e"


def _commit(sha: str, name: str, email: str, files: list[str]) -> str:
    return f"{RS}{sha}{US}{name}{US}{email}\n\n" + "\n".join(files) + "\n"


LOG = "".join(
    [
        _commit("c5", "Ana", "ana@example.com", ["app/auth.py"]),
        _commit("c4", "dependabot[bot]", "49699333+dependabot[bot]@users.noreply.github.com", ["app/auth.py"]),
        _commit("c3", "Ben", "Ben@Example.com", ["app/auth.py", "app/views.py"]),
        _commit("c2", "Ana", "ana@example.com", ["app/auth.py"]),
        _commit("c1", "Cy", "7+cy@users.noreply.github.com", ["app/views.py", "docs/notes.md"]),
    ]
)


def test_parse_log_reads_each_commit_and_its_files() -> None:
    commits = parse_log(LOG)
    assert [c["sha"] for c in commits] == ["c5", "c4", "c3", "c2", "c1"]
    assert commits[2] == {
        "sha": "c3",
        "name": "Ben",
        "email": "ben@example.com",
        "files": ["app/auth.py", "app/views.py"],
    }
    assert parse_log("") == []


def test_noreply_addresses_name_the_account() -> None:
    assert noreply_login("7+cy@users.noreply.github.com") == "cy"
    assert noreply_login("octo@users.noreply.github.com") == "octo"
    assert noreply_login("cy@example.com") is None


def test_ranked_by_files_then_commits_without_bots_or_the_pull_requests_authors() -> None:
    picked = suggest_reviewers(parse_log(LOG), {"app/auth.py", "app/views.py"}, exclude_emails=set())
    assert [(p["name"], p["files"], p["commits"], p["latest_sha"]) for p in picked] == [
        ("Ben", ["app/auth.py", "app/views.py"], 1, "c3"),
        ("Ana", ["app/auth.py"], 2, "c5"),
        ("Cy", ["app/views.py"], 1, "c1"),
    ]
    without_ben = suggest_reviewers(parse_log(LOG), {"app/auth.py"}, exclude_emails={"ben@example.com"}, limit=1)
    assert [p["name"] for p in without_ben] == ["Ana"]
