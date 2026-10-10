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
    assert auth["hunks"] == [{"start": 10, "end": 14}]

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
