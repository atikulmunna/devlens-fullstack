"""Structure-aware code chunking via tree-sitter.

Splits source at top-level definition boundaries (functions, classes, etc.) so each
chunk is a coherent unit instead of an arbitrary line window. Gaps between definitions
(imports, module-level statements) become their own chunks, and any unit larger than the
configured max is further split with a line window so chunk sizes stay bounded.

If tree-sitter or a language grammar is unavailable, chunk_code raises ChunkingUnavailable
and the caller falls back to plain line-window chunking.
"""

try:
    from tree_sitter_language_pack import get_parser
except Exception:  # pragma: no cover - optional dependency path
    get_parser = None


class ChunkingUnavailable(RuntimeError):
    pass


# File extension (or bare filename for extensionless files) -> tree-sitter grammar name.
TS_LANGUAGE_BY_KEY = {
    "py": "python",
    "js": "javascript",
    "jsx": "javascript",
    "ts": "typescript",
    "tsx": "tsx",
    "go": "go",
    "java": "java",
    "cpp": "cpp",
    "hpp": "cpp",
    "c": "c",
    "h": "c",
    "rs": "rust",
    "php": "php",
    "rb": "ruby",
    "cs": "csharp",
}

# Node types that represent a semantic unit worth keeping whole, across languages.
DEFINITION_TYPES = {
    "function_definition",
    "function_declaration",
    "function_item",
    "method_definition",
    "method_declaration",
    "class_definition",
    "class_declaration",
    "class_specifier",
    "struct_specifier",
    "struct_item",
    "interface_declaration",
    "impl_item",
    "trait_item",
    "enum_declaration",
    "enum_specifier",
    "enum_item",
    "constructor_declaration",
    "decorated_definition",
    "namespace_definition",
    "module",
    "type_declaration",
    "abstract_class_declaration",
}


def ts_language_for(key: str) -> str | None:
    return TS_LANGUAGE_BY_KEY.get((key or "").lower())


def _window(start: int, end: int, max_lines: int, overlap_lines: int) -> list[tuple[int, int]]:
    """Line-window an inclusive 1-indexed [start, end] range into <= max_lines pieces."""
    step = max(1, max_lines - overlap_lines)
    spans: list[tuple[int, int]] = []
    cursor = start
    while cursor <= end:
        stop = min(cursor + max_lines - 1, end)
        spans.append((cursor, stop))
        if stop == end:
            break
        cursor = stop + 1 - overlap_lines
        if cursor <= spans[-1][0]:  # safety: never fail to advance
            cursor = stop + 1
    return spans


def chunk_code(content: str, ts_language: str, max_lines: int, overlap_lines: int) -> list[tuple[int, int, str]]:
    if get_parser is None:
        raise ChunkingUnavailable("tree-sitter-language-pack is not installed")
    try:
        parser = get_parser(ts_language)
    except Exception as exc:  # pragma: no cover - grammar load failure
        raise ChunkingUnavailable(f"no grammar for {ts_language}: {exc}") from exc

    lines = content.splitlines()
    total = len(lines)
    if total == 0:
        return []

    tree = parser.parse(content.encode("utf-8", errors="ignore"))
    root = tree.root_node

    # Build ordered spans: definition nodes stay whole; the gaps between them are grouped.
    raw_spans: list[tuple[int, int]] = []
    cursor = 1
    for child in root.named_children:
        start = child.start_point[0] + 1
        end = child.end_point[0] + 1
        if child.type in DEFINITION_TYPES and end >= start:
            if start > cursor:
                raw_spans.append((cursor, start - 1))
            raw_spans.append((start, end))
            cursor = end + 1
    if cursor <= total:
        raw_spans.append((cursor, total))

    if not raw_spans:  # no top-level definitions detected
        raw_spans = [(1, total)]

    # Bound each span to max_lines and materialize non-blank chunks.
    out: list[tuple[int, int, str]] = []
    for start, end in raw_spans:
        pieces = [(start, end)] if (end - start + 1) <= max_lines else _window(start, end, max_lines, overlap_lines)
        for piece_start, piece_end in pieces:
            text = "\n".join(lines[piece_start - 1:piece_end])
            if text.strip():
                out.append((piece_start, piece_end, text))
    return out
