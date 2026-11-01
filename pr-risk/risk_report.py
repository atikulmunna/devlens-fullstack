"""The PR risk comment, rendered from analysis results. Pure: no git, no network."""

from urllib.parse import quote

# Finds the comment again on the next push, so it is updated instead of duplicated.
MARKER = "<!-- devlens-pr-risk -->"
# Longer lists are cut with "and N more", which keeps the comment readable and under GitHub's size limit.
MAX_LISTED = 15
SEVERITY_ORDER = {"high": 0, "medium": 1, "low": 2}


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


def _blob_url(repo: str, sha: str, path: str) -> str:
    return f"https://github.com/{repo}/blob/{sha}/{quote(path)}"


def _code_list(paths: list[str]) -> str:
    shown = ", ".join(f"`{path}`" for path in paths[:MAX_LISTED])
    hidden = len(paths) - MAX_LISTED
    return shown + (f", and {hidden} more" if hidden > 0 else "")


def _inline_code(text: str, limit: int = 90) -> str:
    """Code for a table cell: shortened, pipes escaped, fenced so its own backticks survive."""
    short = text if len(text) <= limit else text[: limit - 3] + "..."
    short = short.replace("|", "\\|")
    return f"`` {short} ``" if "`" in short else f"`{short}`"


def _summary(changed_files: list[dict], flags: list[dict], blast: dict, removed_checks: list[dict]) -> str:
    sentences = [f"{_plural(len(changed_files), 'file')} changed."]
    if removed_checks:
        sentences.append(f"{_plural(len(removed_checks), 'check')} removed, listed first.")
    levels = blast.get("impacted_by_depth") or []
    if levels:
        reach = f", up to {_plural(len(levels), 'import')} away" if len(levels) > 1 else ""
        sentences.append(f"{_plural(blast['impacted_count'], 'other file')} import them{reach}.")
    if flags:
        high = sum(1 for flag in flags if flag["severity"] == "high")
        rated = f", {high} of them high" if high else ""
        sentences.append(f"{_plural(len(flags), 'changed file')} touch security-sensitive code{rated}.")
    if not levels and not flags and not removed_checks:
        sentences.append("Nothing else imports them, and none touch security-sensitive code.")
    return " ".join(sentences)


def _removed_checks_section(repo: str, base_sha: str, checks: list[dict]) -> list[str]:
    if not checks:
        return []
    lines = ["#### Removed checks", "", "| Check | Where it was | Removed line |", "| --- | --- | --- |"]
    for check in checks[: MAX_LISTED * 2]:
        where = f"[`{check['path']}:{check['line']}`]({_blob_url(repo, base_sha, check['path'])}#L{check['line']})"
        kind = check["kind"][0].upper() + check["kind"][1:]
        lines.append(f"| {kind} | {where} | {_inline_code(check['text'])} |")
    hidden = len(checks) - MAX_LISTED * 2
    if hidden > 0:
        lines.append(f"\nAnd {hidden} more.")
    return [*lines, ""]


def _security_section(repo: str, head_sha: str, flags: list[dict]) -> list[str]:
    if not flags:
        return []
    ordered = sorted(flags, key=lambda flag: (SEVERITY_ORDER[flag["severity"]], flag["path"]))
    lines = ["#### Security-sensitive changes", "", "| Severity | File | Touches |", "| --- | --- | --- |"]
    for flag in ordered[: MAX_LISTED * 2]:
        word = flag["severity"].capitalize()
        severity = f"**{word}**" if flag["severity"] == "high" else word
        link = f"[`{flag['path']}`]({_blob_url(repo, head_sha, flag['path'])})"
        lines.append(f"| {severity} | {link} | {', '.join(flag['categories'])} |")
    hidden = len(ordered) - MAX_LISTED * 2
    if hidden > 0:
        lines.append(f"\nAnd {hidden} more files.")
    return [*lines, ""]


def _still_imported_section(repo: str, base_sha: str, still_imported: dict[str, list[str]]) -> list[str]:
    if not still_imported:
        return []
    lines = ["#### Deleted but still imported", ""]
    for path in sorted(still_imported):
        link = f"[`{path}`]({_blob_url(repo, base_sha, path)})"
        lines.append(f"- {link} is deleted, but {_code_list(sorted(still_imported[path]))} still import it.")
    return [*lines, ""]


def _reach_section(blast: dict) -> list[str]:
    levels = blast.get("impacted_by_depth") or []
    if not levels:
        return []
    lines = ["#### What imports the changed files", ""]
    for depth, level in enumerate(levels, start=1):
        label = "Directly" if depth == 1 else f"{depth} imports away"
        lines.append(f"- **{label} ({len(level)}):** {_code_list(level)}")
    return [*lines, ""]


def render_report(
    *,
    repo: str,
    base_sha: str,
    head_sha: str,
    changed_files: list[dict],
    flags: list[dict],
    blast: dict,
    still_imported: dict[str, list[str]],
    removed_checks: list[dict],
    devlens_url: str = "",
) -> str:
    """The comment body. `flags` carry a severity; `blast` comes from blast_radius_from_graph;
    `removed_checks` from diffing.removed_checks (line numbers are in the base)."""
    lines = [MARKER, "### DevLens change risk", "", _summary(changed_files, flags, blast, removed_checks), ""]
    lines += _removed_checks_section(repo, base_sha, removed_checks)
    lines += _security_section(repo, head_sha, flags)
    lines += _still_imported_section(repo, base_sha, still_imported)
    lines += _reach_section(blast)
    footer = f"From the Python and JavaScript/TypeScript import graph at {head_sha[:7]}."
    if devlens_url:
        footer += f" [Open in DevLens]({devlens_url.rstrip('/')}/r/{repo}/changes)"
    lines.append(f"<sub>{footer}</sub>")
    return "\n".join(lines) + "\n"
