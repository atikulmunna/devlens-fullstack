from app.services.dependency_graph import build_dependency_graph


def _edges(files: dict[str, str]) -> set[tuple[str, str]]:
    # Indexed files always have content; empty strings here stand for "any module body".
    rows = [{"file_path": path, "content": content or "# module"} for path, content in files.items()]
    graph = build_dependency_graph(rows)
    return {(edge["source"], edge["target"]) for edge in graph["edges"]}


# --- Python -----------------------------------------------------------------------------------


def test_from_package_import_submodule_reaches_the_submodule() -> None:
    edges = _edges(
        {
            "pkg/__init__.py": "",
            "pkg/signer.py": "class Signer: ...",
            "pkg/timed.py": "x = 1",
            "app.py": "from pkg import signer, timed as t",
        }
    )

    assert edges == {("app.py", "pkg/__init__.py"), ("app.py", "pkg/signer.py"), ("app.py", "pkg/timed.py")}


def test_parenthesized_multiline_from_import() -> None:
    edges = _edges(
        {
            "pkg/__init__.py": "",
            "pkg/a.py": "",
            "pkg/b.py": "",
            "main.py": "from pkg import (\n    a,  # first\n    b,\n)\n",
        }
    )

    assert ("main.py", "pkg/a.py") in edges
    assert ("main.py", "pkg/b.py") in edges


def test_relative_imports_respect_their_level() -> None:
    edges = _edges(
        {
            "src/lib/__init__.py": "",
            "src/lib/core/__init__.py": "",
            "src/lib/core/engine.py": "from . import parts\nfrom .. import util\nfrom ..io.reader import read",
            "src/lib/core/parts.py": "",
            "src/lib/util.py": "",
            "src/lib/io/__init__.py": "",
            "src/lib/io/reader.py": "",
        }
    )

    assert edges >= {
        ("src/lib/core/engine.py", "src/lib/core/parts.py"),
        ("src/lib/core/engine.py", "src/lib/util.py"),
        ("src/lib/core/engine.py", "src/lib/io/reader.py"),
    }


def test_src_layout_and_nested_project_roots() -> None:
    edges = _edges(
        {
            "src/itsdangerous/__init__.py": "from .signer import Signer",
            "src/itsdangerous/signer.py": "",
            "tests/test_signer.py": "from itsdangerous.signer import Signer",
            "backend/app/__init__.py": "",
            "backend/app/services/__init__.py": "",
            "backend/app/services/tokens.py": "",
            "backend/app/api/auth.py": "from app.services.tokens import issue",
        }
    )

    assert ("tests/test_signer.py", "src/itsdangerous/signer.py") in edges
    assert ("backend/app/api/auth.py", "backend/app/services/tokens.py") in edges


def test_stdlib_names_do_not_resolve_to_package_modules() -> None:
    edges = _edges(
        {
            "pkg/__init__.py": "",
            "pkg/json.py": "",
            "app.py": "import json\nfrom typing import List",
        }
    )

    assert edges == set()


def test_script_style_sibling_import() -> None:
    edges = _edges({"scripts/run.py": "import helpers", "scripts/helpers.py": ""})

    assert edges == {("scripts/run.py", "scripts/helpers.py")}


# --- TypeScript and JavaScript ----------------------------------------------------------------


def test_tsconfig_path_alias_resolves_from_the_config_folder() -> None:
    tsconfig = """{
      // Next.js default alias
      "compilerOptions": {
        "paths": { "@/*": ["./*"], },
      },
    }"""
    edges = _edges(
        {
            "frontend/tsconfig.json": tsconfig,
            "frontend/lib/api.ts": "export const x = 1;",
            "frontend/components/chat.tsx": 'import { x } from "@/lib/api";\nimport React from "react";',
            "frontend/app/page.tsx": 'const Chat = dynamic(() => import("@/components/chat"));',
        }
    )

    assert edges == {
        ("frontend/components/chat.tsx", "frontend/lib/api.ts"),
        ("frontend/app/page.tsx", "frontend/components/chat.tsx"),
    }


def test_base_url_resolves_bare_imports_and_paths_use_it() -> None:
    tsconfig = '{"compilerOptions": {"baseUrl": "src", "paths": {"~utils": ["shared/utils/index.ts"]}}}'
    edges = _edges(
        {
            "tsconfig.json": tsconfig,
            "src/services/user.ts": 'import { get } from "services/http";\nimport { pad } from "~utils";',
            "src/services/http.ts": "",
            "src/shared/utils/index.ts": "",
        }
    )

    assert edges == {
        ("src/services/user.ts", "src/services/http.ts"),
        ("src/services/user.ts", "src/shared/utils/index.ts"),
    }


def test_aliases_apply_only_inside_their_config_folder_and_bad_configs_are_skipped() -> None:
    edges = _edges(
        {
            "web/tsconfig.json": '{"compilerOptions": {"paths": {"@/*": ["./*"]}}}',
            "web/lib/a.ts": "",
            "admin/tsconfig.json": "{ not json",
            "admin/page.ts": 'import a from "@/lib/a";',
        }
    )

    assert edges == set()
