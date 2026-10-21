from app.services.blast_radius import compute_blast_radius


def _chunks(files: dict[str, str]) -> list[dict]:
    return [{"file_path": path, "content": content} for path, content in files.items()]


def test_impacted_files_are_transitive_importers() -> None:
    files = _chunks(
        {
            "app/core.py": "def run(): ...",
            "app/service.py": "from app.core import run",
            "app/api.py": "from app.service import handler",
            "app/unrelated.py": "import os",
        }
    )

    blast = compute_blast_radius(files, ["app/core.py"])

    assert blast["changed_files"] == ["app/core.py"]
    assert blast["impacted_files"] == ["app/api.py", "app/service.py"]
    assert blast["impacted_count"] == 2


def test_import_cycle_terminates_and_excludes_changed_file() -> None:
    files = _chunks(
        {
            "app/a.py": "from app.b import thing",
            "app/b.py": "from app.a import other",
        }
    )

    blast = compute_blast_radius(files, ["app/a.py"])

    assert blast["impacted_files"] == ["app/b.py"]


def test_changed_files_are_never_reported_as_impacted() -> None:
    files = _chunks(
        {
            "app/core.py": "def run(): ...",
            "app/service.py": "from app.core import run",
            "app/api.py": "from app.service import handler",
        }
    )

    blast = compute_blast_radius(files, ["app/core.py", "app/service.py"])

    assert blast["changed_files"] == ["app/core.py", "app/service.py"]
    assert blast["impacted_files"] == ["app/api.py"]


def test_unknown_and_empty_paths_have_no_impact() -> None:
    files = _chunks({"app/core.py": "def run(): ...", "app/service.py": "from app.core import run"})

    blast = compute_blast_radius(files, ["deleted/old.py", "", None])

    assert blast["changed_files"] == ["deleted/old.py"]
    assert blast["impacted_files"] == []
    assert blast["impacted_count"] == 0


def test_windows_paths_are_normalized() -> None:
    files = _chunks({"app/core.py": "def run(): ...", "app/service.py": "from app.core import run"})

    blast = compute_blast_radius(files, ["app\\core.py"])

    assert blast["changed_files"] == ["app/core.py"]
    assert blast["impacted_files"] == ["app/service.py"]


def test_relative_javascript_imports_are_followed() -> None:
    files = _chunks(
        {
            "src/lib/util.ts": "export const add = (a, b) => a + b;",
            "src/app.ts": "import { add } from './lib/util';",
            "src/page.tsx": "import App from './app';",
            "src/vendor.ts": "import React from 'react';",
        }
    )

    blast = compute_blast_radius(files, ["src/lib/util.ts"])

    assert blast["impacted_files"] == ["src/app.ts", "src/page.tsx"]
    assert blast["graph_stats"] == {"files_considered": 4, "edges_detected": 2}


def test_impacted_files_are_grouped_by_import_distance() -> None:
    files = _chunks(
        {
            "app/core.py": "def run(): ...",
            "app/service.py": "from app.core import run",
            "app/worker.py": "from app.core import run",
            "app/api.py": "from app.service import handler",
            "app/main.py": "from app.api import router\nfrom app.core import run",
        }
    )

    blast = compute_blast_radius(files, ["app/core.py"])

    # main.py imports core.py directly too, so it sits at distance one, not three.
    assert blast["impacted_by_depth"] == [["app/main.py", "app/service.py", "app/worker.py"], ["app/api.py"]]
