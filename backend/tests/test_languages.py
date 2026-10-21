from app.services.languages import language_name, language_shares


def test_language_names_cover_extensions_and_keep_unknown_keys() -> None:
    assert language_name("py") == "Python"
    assert language_name("TSX") == "TypeScript"
    assert language_name("jsx") == "JavaScript"
    assert language_name("h") == "C"
    assert language_name("dockerfile") == "Dockerfile"
    assert language_name("zig") == "zig"
    assert language_name("  ") is None
    assert language_name(None) is None


def test_shares_merge_by_name_rank_by_size_and_mark_docs() -> None:
    shares = language_shares({"ts": 6.4, "tsx": 7.2, "py": 71.6, "md": 8.8, "yml": 2.9, "yaml": 0.1})

    assert shares == [
        {"name": "Python", "share": 71.6, "is_code": True},
        {"name": "TypeScript", "share": 13.6, "is_code": True},
        {"name": "Markdown", "share": 8.8, "is_code": False},
        {"name": "YAML", "share": 3.0, "is_code": False},
    ]


def test_shares_of_nothing() -> None:
    assert language_shares(None) == []
    assert language_shares({}) == []
