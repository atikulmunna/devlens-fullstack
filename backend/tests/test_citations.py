from app.services.citations import cited_refs, mark_cited


def test_cited_refs_reads_single_grouped_and_adjacent_markers() -> None:
    assert cited_refs("Login is in auth [1]. Tokens [2, 4] and sessions [3][5].") == {1, 2, 3, 4, 5}


def test_cited_refs_ignores_text_without_markers() -> None:
    assert cited_refs("No markers here, only a list[str] type and [x].") == set()
    assert cited_refs("") == set()


def test_mark_cited_flags_each_citation_by_its_ref() -> None:
    citations = [{"ref": 1, "file_path": "a.py"}, {"ref": 2, "file_path": "b.py"}, {"ref": 3, "file_path": "c.py"}]

    marked = mark_cited(citations, "See [3] and [9].")

    assert [citation["cited"] for citation in marked] == [False, False, True]
    assert marked[2]["file_path"] == "c.py"
