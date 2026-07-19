"""Blast-radius analysis: which files are impacted by a set of changed files.

Reuses the import graph from dependency_graph. An edge (source -> target) means source imports
target, so the files impacted by a change to X are the transitive importers of X.
"""

from app.services.dependency_graph import build_dependency_graph


def compute_blast_radius(file_chunks: list[dict], changed_paths: list[str]) -> dict:
    graph = build_dependency_graph(file_chunks)

    # target -> set of files that import it (reverse edges).
    importers: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        importers.setdefault(edge["target"], set()).add(edge["source"])

    changed = {str(path).replace("\\", "/") for path in changed_paths if path}
    impacted: set[str] = set()
    seen: set[str] = set(changed)
    queue: list[str] = list(changed)

    while queue:
        node = queue.pop()
        for importer in importers.get(node, set()):
            if importer in seen:
                continue
            seen.add(importer)
            if importer not in changed:
                impacted.add(importer)
            queue.append(importer)

    return {
        "changed_files": sorted(changed),
        "impacted_files": sorted(impacted),
        "impacted_count": len(impacted),
        "graph_stats": graph.get("stats", {}),
    }
