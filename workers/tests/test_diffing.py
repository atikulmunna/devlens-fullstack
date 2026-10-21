import subprocess

import diffing
from diffing import compute_commit_diff, detect_security_touches, parse_unified_diff

SAMPLE_DIFF = """diff --git a/app/auth.py b/app/auth.py
index 111..222 100644
--- a/app/auth.py
+++ b/app/auth.py
@@ -10,3 +10,5 @@ def login():
-    old = 1
+    token = issue_jwt(user)
+    return token
diff --git a/README.md b/README.md
new file mode 100644
index 000..333
--- /dev/null
+++ b/README.md
@@ -0,0 +1,2 @@
+# Title
+docs
diff --git a/old.py b/old.py
deleted file mode 100644
index 444..000
--- a/old.py
+++ /dev/null
@@ -1,2 +0,0 @@
-print(1)
-print(2)
"""


def test_parse_unified_diff_counts_and_status() -> None:
    files = parse_unified_diff(SAMPLE_DIFF)
    by_path = {f["path"]: f for f in files}

    assert set(by_path) == {"app/auth.py", "README.md", "old.py"}

    auth = by_path["app/auth.py"]
    assert auth["status"] == "modified"
    assert auth["added"] == 2
    assert auth["removed"] == 1
    assert auth["hunks"] == [
        {
            "start": 10,
            "end": 14,
            "old_start": 10,
            "lines": [
                {"kind": "-", "text": "    old = 1", "old": 10},
                {"kind": "+", "text": "    token = issue_jwt(user)", "new": 10},
                {"kind": "+", "text": "    return token", "new": 11},
            ],
        }
    ]

    readme = by_path["README.md"]
    assert readme["status"] == "added"
    assert readme["added"] == 2

    old = by_path["old.py"]
    assert old["status"] == "deleted"
    assert old["removed"] == 2


def test_detect_security_touches_flags_auth_file() -> None:
    files = parse_unified_diff(SAMPLE_DIFF)
    flags = detect_security_touches(files)
    flagged_paths = {f["path"] for f in flags}
    assert "app/auth.py" in flagged_paths
    auth_flag = next(f for f in flags if f["path"] == "app/auth.py")
    assert "auth" in auth_flag["categories"]
    assert "token" in auth_flag["categories"]
    # A pure docs file should not be flagged.
    assert "README.md" not in flagged_paths


def test_empty_diff_returns_no_files() -> None:
    assert parse_unified_diff("") == []


def test_compute_commit_diff_logs_git_failure_reason(monkeypatch, caplog) -> None:
    def fake_run(cmd, **_kwargs):
        if cmd[1] == "rev-parse":
            return subprocess.CompletedProcess(cmd, 0, stdout=b"base-sha\n", stderr=b"")
        if cmd[1] == "diff":
            return subprocess.CompletedProcess(cmd, 128, stdout=b"", stderr=b"fatal: bad object head-sha")
        return subprocess.CompletedProcess(cmd, 0, stdout=b"", stderr=b"")

    monkeypatch.setattr(diffing.subprocess, "run", fake_run)

    assert compute_commit_diff("/tmp/repo", "head-sha") is None
    # Best-effort stays best-effort, but the reason (git's own message) is now recorded.
    assert "Commit diff for head-sha failed: git diff exited 128: fatal: bad object head-sha" in caplog.text


REMOVED_CHECK_DIFF = """diff --git a/app/views.py b/app/views.py
index 111..222 100644
--- a/app/views.py
+++ b/app/views.py
@@ -4,4 +4,3 @@ def delete_account(request):
-    if not verify_token(request):
-        raise Forbidden()
     account.delete()
+    log.info("deleted")
"""


def test_removed_lines_are_captured() -> None:
    by_path = {f["path"]: f for f in parse_unified_diff(SAMPLE_DIFF)}

    assert by_path["app/auth.py"]["removed_lines"] == ["    old = 1"]
    assert by_path["old.py"]["removed_lines"] == ["print(1)", "print(2)"]
    assert by_path["README.md"]["removed_lines"] == []


def test_removed_security_lines_are_flagged_separately() -> None:
    flags = detect_security_touches(parse_unified_diff(REMOVED_CHECK_DIFF))

    # The added line is harmless; the removed token check is the change worth a look.
    assert flags == [{"path": "app/views.py", "categories": ["removed: token"]}]


def test_stored_lines_are_capped_on_both_sides(monkeypatch) -> None:
    removed = "\n".join(f"-r{n}" for n in range(250))
    added = "\n".join(f"+a{n}" for n in range(250))
    diff = f"diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -1,250 +1,250 @@\n{removed}\n{added}\n"

    def fake_run(cmd, **_kwargs):
        stdout = {"rev-parse": b"base-sha\n", "diff": diff.encode()}.get(cmd[1], b"")
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr=b"")

    monkeypatch.setattr(diffing.subprocess, "run", fake_run)

    entry = compute_commit_diff("/tmp/repo", "head-sha")["changed_files"][0]
    assert (entry["added"], entry["removed"]) == (250, 250)
    assert len(entry["added_lines"]) == len(entry["removed_lines"]) == diffing.MAX_STORED_LINES


def test_security_terms_match_snake_case_names_but_not_longer_words() -> None:
    labels = diffing._security_labels

    assert labels("refresh_token = verify_token(req)") == {"token"}
    assert labels("CLIENT_SECRET = load()") == {"secret"}
    assert labels("user.password_hash = bcrypt(pw)") == {"password", "crypto"}
    assert labels("is_authenticated") == {"auth"}
    assert labels("tokenize(text); hashtag; secretary") == set()


CONTEXT_DIFF = '''diff --git a/app/views.py b/app/views.py
--- a/app/views.py
+++ b/app/views.py
@@ -20,4 +20,4 @@ def handler():
     user = load()
-    check_password(user)
+    log(user)
     return user
'''


def test_hunk_lines_carry_old_and_new_line_numbers_with_context() -> None:
    lines = parse_unified_diff(CONTEXT_DIFF)[0]["hunks"][0]["lines"]

    assert lines == [
        {"kind": " ", "text": "    user = load()", "old": 20, "new": 20},
        {"kind": "-", "text": "    check_password(user)", "old": 21},
        {"kind": "+", "text": "    log(user)", "new": 21},
        {"kind": " ", "text": "    return user", "old": 22, "new": 22},
    ]


def test_security_lines_are_labeled_for_the_viewer() -> None:
    files = parse_unified_diff(CONTEXT_DIFF)
    diffing.label_security_lines(files)

    labeled = [(line["kind"], line.get("labels")) for line in files[0]["hunks"][0]["lines"]]
    assert labeled == [(" ", None), ("-", ["password"]), ("+", None), (" ", None)]


def test_hunk_lines_are_capped_per_file_and_per_commit(monkeypatch) -> None:
    monkeypatch.setattr(diffing, "MAX_HUNK_LINES_PER_FILE", 3)
    big = "\n".join(f"+a{n}" for n in range(5))
    diff = f"diff --git a/x.py b/x.py\n--- a/x.py\n+++ b/x.py\n@@ -0,0 +1,5 @@\n{big}\n"
    entry = parse_unified_diff(diff)[0]
    assert (entry["added"], len(entry["hunks"][0]["lines"]), entry["truncated"]) == (5, 3, True)

    monkeypatch.setattr(diffing, "MAX_HUNK_LINES_PER_DIFF", 4)
    files = parse_unified_diff(diff + diff.replace("x.py", "y.py"))
    diffing._cap_hunk_lines(files)
    assert [len(f["hunks"][0]["lines"]) for f in files] == [3, 0]
    assert [f["truncated"] for f in files] == [True, True]
    assert "hunk_line_count" not in files[0]


def test_docs_and_stylesheets_are_not_flagged_as_security_changes() -> None:
    files = [
        {"path": "README.md", "added_lines": ["Set JWT_SECRET and OAUTH_TOKEN"], "removed_lines": [], "hunks": []},
        {"path": ".env.example", "added_lines": ["JWT_SECRET=change-me"], "removed_lines": [], "hunks": []},
        {"path": "web/globals.css", "added_lines": [".auth { margin: 0 }"], "removed_lines": [], "hunks": []},
    ]

    assert [flag["path"] for flag in detect_security_touches(files)] == [".env.example"]
