"""What kind of file a path is, from the path alone. Standard library only: the PR risk Action
(pr-risk/) uses it on a bare CI runner, where the parsers in chunking are not installed."""

import re

TEST_DIRS = {"test", "tests", "__tests__", "spec"}
TEST_FILE_PATTERN = re.compile(r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$)")


def is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    return any(part in TEST_DIRS for part in parts[:-1]) or bool(TEST_FILE_PATTERN.search(parts[-1]))
