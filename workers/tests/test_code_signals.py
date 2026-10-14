from code_signals import count_todos, find_long_functions, is_test_path


def _body(lines: int, indent: str = "    ") -> str:
    return "\n".join(f"{indent}x = {n}" for n in range(lines))


def test_python_methods_and_nested_functions_are_measured() -> None:
    source = (
        "class Service:\n"
        "    def short(self):\n"
        "        return 1\n\n"
        "    @cached\n"
        "    def long_method(self):\n"
        f"{_body(55, '        ')}\n\n"
        "def outer():\n"
        "    def inner():\n"
        f"{_body(60, '        ')}\n"
        "    return inner\n"
    )

    found = find_long_functions(source, "py")

    assert [(f["name"], f["length"]) for f in found] == [("long_method", 56), ("outer", 63), ("inner", 61)]


def test_javascript_named_arrow_functions_and_methods_count() -> None:
    body = _body(55, "  ").replace("x =", "let x =")
    source = (
        f"const handler = () => {{\n{body}\n}};\n"
        f"class Api {{\n  fetchAll() {{\n{body}\n  }}\n}}\n"
        f"[1].map(() => {{\n{body}\n}});\n"
    )

    names = [f["name"] for f in find_long_functions(source, "js")]

    assert names == ["handler", "fetchAll"]


def test_go_and_c_names_are_found() -> None:
    go_body = "\n".join(f"\tx{n} := {n}\n\t_ = x{n}" for n in range(30))
    go_source = f"package main\n\nfunc (s *Server) Serve() {{\n{go_body}\n}}\n"
    c_body = "\n".join(f"  int x{n} = {n};" for n in range(55))
    c_source = f"static int *parse_all(char *s) {{\n{c_body}\n  return 0;\n}}\n"

    assert [f["name"] for f in find_long_functions(go_source, "go")] == ["Serve"]
    assert [f["name"] for f in find_long_functions(c_source, "c")] == ["parse_all"]


def test_short_functions_and_unknown_languages_are_skipped() -> None:
    assert find_long_functions("def f():\n    return 1\n", "py") == []
    assert find_long_functions(_body(80), "md") == []


def test_todos_counted_once_in_code_and_never_in_prose() -> None:
    code = "# TODO: retry\nx = 1  # fixme later\n# todoist is not a note\n"

    assert count_todos(code, "py") == 2
    assert count_todos("- TODO: write docs", "md") == 0
    assert count_todos("TODO", "rst") == 0


def test_test_paths() -> None:
    for path in ("tests/test_api.py", "src/__tests__/a.ts", "pkg/server_test.go", "web/app.spec.tsx", "test_x.py"):
        assert is_test_path(path), path
    for path in ("src/latest_version.py", "contest/main.py", "src/testing_utils.py"):
        assert not is_test_path(path), path
