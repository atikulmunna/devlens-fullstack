"""Hotspots: code that changes often and that many other files import.

A change there is both likely and far-reaching, so it is where hard-to-change code costs the most.
Churn comes from the analysis (the parse stage counts commits per file over a window); coupling
is how many files import the file, from the import graph.
"""

from app.services.blast_radius import importers_by_file
from app.services.dependency_graph import JS_EXTENSIONS

# One change in the window is not a pattern.
MIN_CHANGES = 2


def rank_hotspots(churn: dict[str, int], graph: dict, limit: int = 10) -> list[dict]:
    """Code files ranked by changes x (1 + importers). Lock files and changelogs churn too, but are not code."""
    code = {node["id"] for node in graph["nodes"] if node["id"].endswith((".py", *JS_EXTENSIONS))}
    importers = importers_by_file(graph)
    ranked = []
    for path, changes in churn.items():
        if path not in code or changes < MIN_CHANGES:
            continue
        count = len(importers.get(path, ()))
        ranked.append({"path": path, "changes": changes, "importers": count, "score": changes * (1 + count)})
    ranked.sort(key=lambda hotspot: (-hotspot["score"], -hotspot["changes"], hotspot["path"]))
    return ranked[:limit]
