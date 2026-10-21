"""Display names for the language keys the parse worker records (a file extension, or a file name)."""

LANGUAGE_NAMES = {
    "py": "Python",
    "python": "Python",
    "js": "JavaScript",
    "jsx": "JavaScript",
    "javascript": "JavaScript",
    "ts": "TypeScript",
    "tsx": "TypeScript",
    "go": "Go",
    "java": "Java",
    "rb": "Ruby",
    "rs": "Rust",
    "c": "C",
    "h": "C",
    "cpp": "C++",
    "hpp": "C++",
    "c++": "C++",
    "cs": "C#",
    "c#": "C#",
    "php": "PHP",
    "kt": "Kotlin",
    "swift": "Swift",
    "scala": "Scala",
    "sh": "Shell",
    "bash": "Shell",
    "sql": "SQL",
    "tf": "Terraform",
    "makefile": "Makefile",
    "dockerfile": "Dockerfile",
    "md": "Markdown",
    "rst": "reStructuredText",
    "toml": "TOML",
    "yml": "YAML",
    "yaml": "YAML",
    "json": "JSON",
    "ini": "INI",
    "cfg": "INI",
}

# Documentation and configuration formats: present in most repos, but not what a project is "written in".
NON_CODE_LANGUAGES = {
    "Markdown",
    "reStructuredText",
    "YAML",
    "JSON",
    "TOML",
    "INI",
    "Dockerfile",
    "txt",
    "unknown",
}


def language_name(key: str | None) -> str | None:
    if not key or not key.strip():
        return None
    raw = key.strip()
    return LANGUAGE_NAMES.get(raw.lower(), raw)


def language_shares(breakdown: dict | None) -> list[dict]:
    """The breakdown merged by display name, largest first, in percent of the indexed size."""
    merged: dict[str, float] = {}
    for key, share in (breakdown or {}).items():
        name = language_name(key)
        if name:
            merged[name] = merged.get(name, 0.0) + float(share or 0)
    ranked = sorted(merged.items(), key=lambda kv: kv[1], reverse=True)
    return [
        {"name": name, "share": round(share, 2), "is_code": name not in NON_CODE_LANGUAGES} for name, share in ranked
    ]
