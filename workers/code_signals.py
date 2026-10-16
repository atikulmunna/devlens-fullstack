"""Per-file code health signals, computed from whole files while parsing.

Chunks overlap and split long definitions, so signals counted from chunks double count and
miss methods. The parse stage still has each file whole, so it measures here instead.
"""

import re

from chunking import get_parser, ts_language_for

LONG_FUNCTION_LINES = 50

# Named function-like nodes across the tree-sitter grammars in chunking.TS_LANGUAGE_BY_KEY.
FUNCTION_TYPES = {
    "function_definition",
    "function_declaration",
    "generator_function_declaration",
    "method_definition",
    "method_declaration",
    "constructor_declaration",
    "function_item",
    "method",
    "singleton_method",
}
# Anonymous functions count when assigned to a name: `const handler = () => {...}`.
ASSIGNED_FUNCTION_TYPES = {"arrow_function", "function_expression", "function"}

# Prose files: a TODO in a changelog or guide is not a code note.
DOC_EXTENSIONS = {"md", "rst", "txt", "adoc"}
TODO_PATTERN = re.compile(r"\b(TODO|FIXME)\b", re.IGNORECASE)

TEST_DIRS = {"test", "tests", "__tests__", "spec"}
TEST_FILE_PATTERN = re.compile(r"(^test_.*\.py$|_test\.(py|go)$|\.(test|spec)\.[jt]sx?$)")


def _node_text(node) -> str:
    return node.text.decode("utf-8", errors="ignore") if node is not None and node.text else ""


def _function_name(node) -> str:
    if node.type in ASSIGNED_FUNCTION_TYPES:
        return _node_text(node.parent.child_by_field_name("name"))
    name = node.child_by_field_name("name")
    if name is not None:
        return _node_text(name)
    # C and C++ keep the name inside nested declarators: int *parse(char *s) {...}
    declarator = node.child_by_field_name("declarator")
    while declarator is not None and declarator.child_by_field_name("declarator") is not None:
        declarator = declarator.child_by_field_name("declarator")
    return _node_text(declarator)


def _is_function(node) -> bool:
    if node.type in FUNCTION_TYPES:
        return True
    return (
        node.type in ASSIGNED_FUNCTION_TYPES and node.parent is not None and node.parent.type == "variable_declarator"
    )


def find_long_functions(content: str, language_key: str, min_lines: int = LONG_FUNCTION_LINES) -> list[dict]:
    """Functions and methods at any depth spanning more than min_lines lines."""
    ts_language = ts_language_for(language_key)
    if get_parser is None or ts_language is None:
        return []
    try:
        tree = get_parser(ts_language).parse(content.encode("utf-8", errors="ignore"))
    except Exception:  # noqa: BLE001 - a grammar failure leaves this file unmeasured
        return []

    found: list[dict] = []
    stack = [tree.root_node]
    while stack:
        node = stack.pop()
        if _is_function(node):
            length = node.end_point[0] - node.start_point[0] + 1
            if length > min_lines:
                found.append(
                    {"name": _function_name(node) or "(anonymous)", "line": node.start_point[0] + 1, "length": length}
                )
        stack.extend(node.named_children)
    return sorted(found, key=lambda item: item["line"])


def count_todos(content: str, language_key: str) -> int:
    if (language_key or "").lower() in DOC_EXTENSIONS:
        return 0
    return len(TODO_PATTERN.findall(content))


def is_test_path(path: str) -> bool:
    parts = path.lower().split("/")
    return any(part in TEST_DIRS for part in parts[:-1]) or bool(TEST_FILE_PATTERN.search(parts[-1]))
