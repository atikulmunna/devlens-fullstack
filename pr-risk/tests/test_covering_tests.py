from covering_tests import covering_tests
from file_kinds import is_test_path


def _graph(edges: list[tuple[str, str]], extra_nodes: tuple[str, ...] = ()) -> dict:
    nodes = {path for edge in edges for path in edge} | set(extra_nodes)
    return {
        "nodes": [{"id": path} for path in sorted(nodes)],
        "edges": [{"source": source, "target": target} for source, target in edges],
    }


GRAPH = _graph(
    [
        ("tests/test_views.py", "app/views.py"),
        ("app/views.py", "app/auth.py"),
        ("app/api.py", "app/views.py"),
        ("web/cart.test.ts", "web/cart.ts"),
    ],
    extra_nodes=("app/payments.py", "app/__init__.py", "web/types.d.ts", "tests/test_payments_todo.py"),
)


def test_tests_that_reach_the_change_through_any_chain_are_listed_to_run() -> None:
    # app/auth.py changed: app/views.py imports it, and tests/test_views.py imports app/views.py.
    result = covering_tests(GRAPH, ["app/auth.py"], ["app/views.py", "app/api.py", "tests/test_views.py"], is_test_path)
    assert result == {"tests_to_run": ["tests/test_views.py"], "untested": []}


def test_changed_files_no_test_reaches_are_listed() -> None:
    changed = ["app/payments.py", "web/cart.ts", "app/__init__.py", "web/types.d.ts", "README.md"]
    result = covering_tests(GRAPH, changed, [], is_test_path)
    # web/cart.ts has a test; package markers, type declarations, and non-code files are not listed.
    assert result["untested"] == ["app/payments.py"]
    assert result["tests_to_run"] == []


def test_a_changed_test_is_run_and_never_called_untested() -> None:
    result = covering_tests(GRAPH, ["tests/test_payments_todo.py"], [], is_test_path)
    assert result == {"tests_to_run": ["tests/test_payments_todo.py"], "untested": []}
