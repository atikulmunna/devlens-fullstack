"""Blast-radius analysis: which files are impacted by a set of changed files.

Reuses the import graph from dependency_graph. An edge (source -> target) means source imports
target, so the files impacted by a change to X are the transitive importers of X.
"""

from app.services.dependency_graph import build_dependency_graph


def importers_by_file(graph: dict) -> dict[str, set[str]]:
    """target -> the files that import it (the graph's edges, reversed)."""
    importers: dict[str, set[str]] = {}
    for edge in graph["edges"]:
        importers.setdefault(edge["target"], set()).add(edge["source"])
    return importers


def blast_radius_from_graph(graph: dict, changed_paths: list[str]) -> dict:
    importers = importers_by_file(graph)
    changed = {str(path).replace("\\", "/") for path in changed_paths if path}
    seen: set[str] = set(changed)
    # Breadth first, so each impacted file sits at its shortest import distance from a change.
    by_depth: list[list[str]] = []
    frontier = sorted(changed)
    while frontier:
        next_level = sorted({importer for node in frontier for importer in importers.get(node, set())} - seen)
        if next_level:
            by_depth.append(next_level)
            seen.update(next_level)
        frontier = next_level

    impacted = sorted(path for level in by_depth for path in level)
    return {
        "changed_files": sorted(changed),
        "impacted_files": impacted,
        "impacted_count": len(impacted),
        # impacted_by_depth[0] imports a changed file directly, [1] imports one of those, and so on.
        "impacted_by_depth": by_depth,
        "graph_stats": graph.get("stats", {}),
    }


def compute_blast_radius(file_chunks: list[dict], changed_paths: list[str]) -> dict:
    return blast_radius_from_graph(build_dependency_graph(file_chunks), changed_paths)
