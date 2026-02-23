import os
import posixpath
import re

PY_IMPORT_RE = re.compile(r"^\s*import\s+([^\n#]+)", re.MULTILINE)
PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+([a-zA-Z0-9_\.]+)\s+import\s+", re.MULTILINE)
JS_IMPORT_RE = re.compile(r"""(?:import|export)\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]""")
JS_REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")


def _to_module_path(file_path: str) -> str:
    path = file_path.replace("\\", "/")
    if path.endswith(".py"):
        path = path[:-3]
    return path.replace("/", ".")


def _resolve_python_import(source_file: str, imported_module: str, files: set[str]) -> str | None:
    # Resolve direct module path to file (pkg.mod -> pkg/mod.py).
    candidate = imported_module.strip(".").replace(".", "/")
    if not candidate:
        return None
    candidate_file = f"{candidate}.py"
    if candidate_file in files:
        return candidate_file

    # Resolve package __init__ style fallback.
    package_init = f"{candidate}/__init__.py"
    if package_init in files:
        return package_init

    # Resolve same-prefix module in analyzed files.
    source_dir = posixpath.dirname(source_file)
    if source_dir:
        local_candidate = posixpath.normpath(posixpath.join(source_dir, candidate_file))
        if local_candidate in files:
            return local_candidate

    return None


def _resolve_js_import(source_file: str, imported_ref: str, files: set[str]) -> str | None:
    if not imported_ref.startswith("."):
        return None

    base_dir = posixpath.dirname(source_file)
    base_path = posixpath.normpath(posixpath.join(base_dir, imported_ref))
    candidates: list[str] = []

    if any(base_path.endswith(ext) for ext in JS_EXTENSIONS):
        candidates.append(base_path)
    else:
        for ext in JS_EXTENSIONS:
            candidates.append(base_path + ext)
            candidates.append(posixpath.join(base_path, f"index{ext}"))

    for candidate in candidates:
        if candidate in files:
            return candidate
    return None


def build_dependency_graph(file_chunks: list[dict]) -> dict:
    file_to_content: dict[str, list[str]] = {}
    for row in file_chunks:
        file_path = str(row.get("file_path") or "").replace("\\", "/")
        content = str(row.get("content") or "")
        if not file_path or not content:
            continue
        file_to_content.setdefault(file_path, []).append(content)

    files = set(file_to_content.keys())
    nodes = [{"id": path, "label": os.path.basename(path), "file_path": path} for path in sorted(files)]
    edge_set: set[tuple[str, str, str]] = set()

    for file_path, chunks in file_to_content.items():
        if file_path.endswith(".py"):
            merged = "\n".join(chunks)
            for match in PY_IMPORT_RE.findall(merged):
                for module in [p.strip() for p in match.split(",") if p.strip()]:
                    if " as " in module:
                        module = module.split(" as ", 1)[0].strip()
                    target = _resolve_python_import(file_path, module, files)
                    if target and target != file_path:
                        edge_set.add((file_path, target, "python"))
            for module in PY_FROM_IMPORT_RE.findall(merged):
                target = _resolve_python_import(file_path, module, files)
                if target and target != file_path:
                    edge_set.add((file_path, target, "python"))

        if file_path.endswith(JS_EXTENSIONS):
            merged = "\n".join(chunks)
            refs = JS_IMPORT_RE.findall(merged) + JS_REQUIRE_RE.findall(merged)
            for ref in refs:
                target = _resolve_js_import(file_path, ref, files)
                if target and target != file_path:
                    edge_set.add((file_path, target, "javascript"))

    edges = [
        {"id": f"{src}->{dst}", "source": src, "target": dst, "kind": kind}
        for src, dst, kind in sorted(edge_set)
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "files_considered": len(nodes),
            "edges_detected": len(edges),
        },
    }
