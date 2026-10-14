import json
import os
import posixpath
import re

PY_IMPORT_RE = re.compile(r"^\s*import\s+([^\n#]+)", re.MULTILINE)
# `from X import a, b` and the parenthesized multi-line form; X may be relative (`.`, `..pkg`).
PY_FROM_IMPORT_RE = re.compile(r"^\s*from\s+(\.*[a-zA-Z0-9_\.]*)\s+import\s+(\([^)]*\)|[^\n#]+)", re.MULTILINE)
JS_IMPORT_RE = re.compile(r"""(?:import|export)\s+(?:[^'"]+?\s+from\s+)?['"]([^'"]+)['"]""")
JS_REQUIRE_RE = re.compile(r"""require\(\s*['"]([^'"]+)['"]\s*\)""")
JS_DYNAMIC_IMPORT_RE = re.compile(r"""import\(\s*['"]([^'"]+)['"]\s*\)""")

JS_EXTENSIONS = (".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")
TS_CONFIG_NAMES = ("tsconfig.json", "jsconfig.json")
# Strings are kept, // and /* */ comments dropped: tsconfig allows comments, json.loads does not.
_JSON_STRING_OR_COMMENT_RE = re.compile(r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*.*?\*/', re.DOTALL)
_TRAILING_COMMA_RE = re.compile(r",(\s*[}\]])")


class _Files:
    """The analyzed file set, with a basename index for suffix lookups."""

    def __init__(self, paths: set[str]):
        self.paths = paths
        self.by_basename: dict[str, list[str]] = {}
        for path in paths:
            self.by_basename.setdefault(posixpath.basename(path), []).append(path)

    def __contains__(self, path: str) -> bool:
        return path in self.paths

    def under_source_root(self, suffix: str) -> str | None:
        """The shortest file ending in `suffix` whose top package starts at a source root.

        `app/services/x.py` matches `backend/app/services/x.py` (backend/ is not a package), but
        `json.py` does not match `pkg/json.py` when pkg/ is a package: that would be pkg.json.
        """
        matches = []
        for path in self.by_basename.get(posixpath.basename(suffix), []):
            if path != suffix and not path.endswith("/" + suffix):
                continue
            prefix = path[: len(path) - len(suffix)]
            if not prefix or f"{prefix}__init__.py" not in self.paths:
                matches.append(path)
        return min(matches, key=lambda p: (len(p), p)) if matches else None


# --- Python -----------------------------------------------------------------------------------


def _python_module_file(source_file: str, module: str, files: _Files) -> str | None:
    """Resolve a module name (absolute, or relative with leading dots) to its file."""
    level = len(module) - len(module.lstrip("."))
    rel = module.lstrip(".").replace(".", "/")

    if level:
        base = posixpath.dirname(source_file)
        for _ in range(level - 1):
            base = posixpath.dirname(base)
        stem = posixpath.join(base, rel) if rel else base
        for candidate in (f"{stem}.py", posixpath.join(stem, "__init__.py")):
            if posixpath.normpath(candidate) in files:
                return posixpath.normpath(candidate)
        return None

    if not rel:
        return None
    for suffix in (f"{rel}.py", f"{rel}/__init__.py"):
        if suffix in files:
            return suffix
        # Script-style sibling: `import utils` next to utils.py in a folder that is not a package.
        sibling = posixpath.join(posixpath.dirname(source_file), suffix)
        if sibling in files:
            return sibling
    for suffix in (f"{rel}.py", f"{rel}/__init__.py"):
        found = files.under_source_root(suffix)
        if found:
            return found
    return None


def _imported_names(raw: str) -> list[str]:
    names = []
    without_comments = re.sub(r"#[^\n]*", "", raw)
    for part in without_comments.strip().strip("()").split(","):
        name = part.strip().split(" as ", 1)[0].strip()
        if name and name != "*":
            names.append(name)
    return names


def _python_edges(file_path: str, source: str, files: _Files) -> set[str]:
    targets: set[str] = set()
    for match in PY_IMPORT_RE.findall(source):
        for module in _imported_names(match):
            targets.add(_python_module_file(file_path, module, files))
    for module, raw_names in PY_FROM_IMPORT_RE.findall(source):
        module_file = _python_module_file(file_path, module, files)
        targets.add(module_file)
        # `from pkg import submodule` imports pkg/submodule.py, not only pkg/__init__.py.
        joiner = "" if module.endswith(".") else "."
        for name in _imported_names(raw_names):
            targets.add(_python_module_file(file_path, f"{module}{joiner}{name}", files))
    return targets


# --- JavaScript and TypeScript ----------------------------------------------------------------


def _parse_ts_config(config_path: str, text: str) -> dict | None:
    cleaned = _JSON_STRING_OR_COMMENT_RE.sub(lambda m: m.group(0) if m.group(0).startswith('"') else "", text)
    try:
        options = json.loads(_TRAILING_COMMA_RE.sub(r"\1", cleaned)).get("compilerOptions") or {}
    except (ValueError, AttributeError):
        return None
    config_dir = posixpath.dirname(config_path)
    base_url = options.get("baseUrl")
    return {
        "dir": config_dir,
        # paths resolve against baseUrl when set, otherwise against the config's own folder.
        "base": posixpath.normpath(posixpath.join(config_dir, base_url)) if base_url else config_dir,
        "has_base_url": bool(base_url),
        "paths": options.get("paths") or {},
    }


def _alias_bases(config: dict, ref: str) -> list[str]:
    bases = []
    for pattern, targets in config["paths"].items():
        if "*" in pattern:
            prefix, suffix = pattern.split("*", 1)
            if not (ref.startswith(prefix) and ref.endswith(suffix) and len(ref) >= len(prefix) + len(suffix)):
                continue
            star = ref[len(prefix): len(ref) - len(suffix)]
            bases += [target.replace("*", star, 1) for target in targets]
        elif ref == pattern:
            bases += list(targets)
    if config["has_base_url"]:
        bases.append(ref)
    return [posixpath.normpath(posixpath.join(config["base"], base)) for base in bases]


def _js_module_file(base_path: str, files: _Files) -> str | None:
    candidates = [base_path] if base_path.endswith(JS_EXTENSIONS) else []
    for ext in JS_EXTENSIONS:
        candidates += [base_path + ext, posixpath.join(base_path, f"index{ext}")]
    return next((candidate for candidate in candidates if candidate in files), None)


def _resolve_js_import(source_file: str, ref: str, files: _Files, ts_configs: list[dict]) -> str | None:
    if ref.startswith("."):
        return _js_module_file(posixpath.normpath(posixpath.join(posixpath.dirname(source_file), ref)), files)
    # The nearest config that contains the importing file decides its aliases.
    for config in ts_configs:
        if config["dir"] and not source_file.startswith(config["dir"] + "/"):
            continue
        for base in _alias_bases(config, ref):
            found = _js_module_file(base, files)
            if found:
                return found
        return None
    return None


def _js_edges(file_path: str, source: str, files: _Files, ts_configs: list[dict]) -> set[str]:
    refs = JS_IMPORT_RE.findall(source) + JS_REQUIRE_RE.findall(source) + JS_DYNAMIC_IMPORT_RE.findall(source)
    return {_resolve_js_import(file_path, ref, files, ts_configs) for ref in refs}


# --- Graph ------------------------------------------------------------------------------------


def build_dependency_graph(file_chunks: list[dict]) -> dict:
    file_to_content: dict[str, list[str]] = {}
    for row in file_chunks:
        file_path = str(row.get("file_path") or "").replace("\\", "/")
        content = str(row.get("content") or "")
        if not file_path or not content:
            continue
        file_to_content.setdefault(file_path, []).append(content)

    files = _Files(set(file_to_content.keys()))
    ts_configs = [
        config
        for path, chunks in file_to_content.items()
        if posixpath.basename(path) in TS_CONFIG_NAMES
        for config in [_parse_ts_config(path, "\n".join(chunks))]
        if config
    ]
    ts_configs.sort(key=lambda config: len(config["dir"]), reverse=True)

    nodes = [{"id": path, "label": os.path.basename(path), "file_path": path} for path in sorted(files.paths)]
    edge_set: set[tuple[str, str, str]] = set()
    for file_path, chunks in file_to_content.items():
        source = "\n".join(chunks)
        if file_path.endswith(".py"):
            edge_set |= {(file_path, target, "python") for target in _python_edges(file_path, source, files)}
        if file_path.endswith(JS_EXTENSIONS):
            edge_set |= {(file_path, target, "javascript") for target in _js_edges(file_path, source, files, ts_configs)}

    edges = [
        {"id": f"{src}->{dst}", "source": src, "target": dst, "kind": kind}
        for src, dst, kind in sorted(edge for edge in edge_set if edge[1] and edge[1] != edge[0])
    ]

    return {
        "nodes": nodes,
        "edges": edges,
        "stats": {
            "files_considered": len(nodes),
            "edges_detected": len(edges),
        },
    }
