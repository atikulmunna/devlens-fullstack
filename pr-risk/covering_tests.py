"""Which tests exercise a change, and which changed files no test reaches, from the import graph.

A test exercises a file when it imports it, directly or through other files. That says nothing
about how well the file is tested, only that some test loads it.
"""

from collections.abc import Callable

# Files a test rarely imports by name; listing them as untested would be noise.
_NEVER_UNTESTED = ("__init__.py", ".d.ts")


def _reachable(edges: list[dict], starts: set[str]) -> set[str]:
    """Every file the starting files import, directly or through other files."""
    imports: dict[str, set[str]] = {}
    for edge in edges:
        imports.setdefault(edge["source"], set()).add(edge["target"])
    seen, frontier = set(starts), list(starts)
    while frontier:
        nxt = {target for node in frontier for target in imports.get(node, set())} - seen
        seen |= nxt
        frontier = list(nxt)
    return seen


def covering_tests(graph: dict, changed: list[str], impacted: list[str], is_test: Callable[[str], bool]) -> dict:
    """`changed` are the changed files still present; `impacted` their importers (blast radius)."""
    in_graph = {node["id"] for node in graph["nodes"]}
    tests = {path for path in in_graph if is_test(path)}
    covered = _reachable(graph["edges"], tests)
    untested = [
        path
        for path in changed
        if path in in_graph and path not in covered and not is_test(path) and not path.endswith(_NEVER_UNTESTED)
    ]
    return {
        # A changed test, or a test that imports the change through any chain: these are the ones to run.
        "tests_to_run": sorted(tests & (set(changed) | set(impacted))),
        "untested": sorted(untested),
    }
