import pytest

import chunking
from chunking import ChunkingUnavailable, chunk_code, ts_language_for


def test_ts_language_mapping() -> None:
    assert ts_language_for("py") == "python"
    assert ts_language_for("TSX") == "tsx"
    assert ts_language_for("md") is None


def test_window_bounds_and_advances() -> None:
    spans = chunking._window(1, 10, max_lines=4, overlap_lines=1)
    # Every span is within [1, 10], bounded to <= 4 lines, and covers the last line.
    assert all(1 <= s <= e <= 10 for s, e in spans)
    assert all((e - s + 1) <= 4 for s, e in spans)
    assert spans[-1][1] == 10


def test_chunk_code_unavailable_without_grammar(monkeypatch) -> None:
    monkeypatch.setattr(chunking, "get_parser", None)
    with pytest.raises(ChunkingUnavailable):
        chunk_code("def f():\n    return 1\n", "python", 120, 20)


PYTHON_SAMPLE = '''import os


def alpha():
    return 1


class Beta:
    def method(self):
        return 2
'''


def test_chunk_code_splits_python_at_definitions() -> None:
    pytest.importorskip("tree_sitter_language_pack")
    spans = chunk_code(PYTHON_SAMPLE, "python", 120, 20)
    texts = [t for _, _, t in spans]
    # The top-level function and class land in separate chunks.
    assert any("def alpha" in t and "class Beta" not in t for t in texts)
    assert any("class Beta" in t for t in texts)
    # All spans are 1-indexed and ordered.
    starts = [s for s, _, _ in spans]
    assert starts == sorted(starts)
    assert min(starts) >= 1
