"""How chat answers a question: route it, choose and number the contexts, and fall back.

Questions about languages are answered from the analysis breakdown; everything else becomes a plan
for the model (summary or answer mode, numbered contexts, their citations). The router streams it.
"""

import re
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AnalysisResult, CodeChunk
from app.services.chat_synthesizer import MAX_CONTEXTS, detect_intent
from app.services.citations import format_citation, validate_citations_for_repo
from app.services.retrieval_hybrid import load_chunk_content


def _normalize_language(raw: str | None) -> str | None:
    if not raw:
        return None
    key = raw.strip().lower()
    aliases = {
        "py": "Python",
        "python": "Python",
        "js": "JavaScript",
        "javascript": "JavaScript",
        "ts": "TypeScript",
        "tsx": "TypeScript",
        "jsx": "JavaScript (React JSX)",
        "go": "Go",
        "java": "Java",
        "rb": "Ruby",
        "rs": "Rust",
        "c": "C",
        "cpp": "C++",
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
        "md": "Markdown",
        "rst": "reStructuredText",
        "toml": "TOML",
        "makefile": "Makefile",
        "yml": "YAML",
        "yaml": "YAML",
        "json": "JSON",
    }
    return aliases.get(key, raw.strip())


# Documentation and configuration formats: present in most repos, but not what a project is "written in".
NON_CODE_LANGUAGES = {"Markdown", "reStructuredText", "YAML", "JSON", "TOML", "txt", "unknown"}


def _language_answer(breakdown: dict | None) -> str | None:
    """Describe the repo's code languages from the analysis breakdown (percent of indexed size)."""
    shares: dict[str, float] = {}
    for key, share in (breakdown or {}).items():
        name = _normalize_language(key)
        if name and name not in NON_CODE_LANGUAGES:
            shares[name] = shares.get(name, 0.0) + float(share or 0)
    total = sum(shares.values())
    if total <= 0:
        return None

    ranked = sorted(shares.items(), key=lambda kv: kv[1], reverse=True)

    def _describe(name: str, share: float) -> str:
        percent = share / total * 100
        return f"{name} ({'under 1' if percent < 1 else round(percent)}%)"

    lead_name, lead_share = ranked[0]
    if len(ranked) == 1:
        return f"The code is written in {lead_name}."
    rest = ", ".join(_describe(name, share) for name, share in ranked[1:4])
    return (
        f"The code is mostly {_describe(lead_name, lead_share)}, with {rest}. Shares are by size of the indexed code."
    )


def _language_question(query: str) -> bool:
    # Phrases only: a bare "stack" or "language" also matches "stack trace" or "language model".
    q = query.lower()
    patterns = (
        "what language",
        "which language",
        "programming language",
        "languages",
        "tech stack",
        "built with",
        "written in",
    )
    return any(token in q for token in patterns)


# Questions about the whole repository, answered in summary mode with the README first. Broad
# phrasings like "main architecture components" retrieve config and CI files on their own.
REPO_WIDE_QUESTION_RE = re.compile(
    r"summari[sz]e|summary|high[- ]level|overview|purpose|runtime flow|output format"
    # "main components" or "main components of this repo", but not "main components of the signer"
    r"|\b(main|core|key|overall)\s+(architecture|components?|modules?|parts|pieces|building blocks)\b"
    r"(?!\s+(of|in|for)\s+(?!(this|the)\s+(repo|repository|project|codebase|library|app)\b))"
    r"|\barchitecture\s+(of|for)\s+(this|the)\s+(repo|repository|project|codebase)\b"
    r"|\b(repo|repository|project|codebase)\s+(structure|layout|architecture)\b"
    r"|\bhow\s+is\s+(this|the)\s+(repo|repository|project|codebase)\s+(organi[sz]ed|structured|laid out)\b"
    r"|\bwhat\s+(does|is)\s+this\s+(repo|repository|project|codebase|library)\b",
    re.IGNORECASE,
)


def _summary_question(query: str) -> bool:
    return bool(REPO_WIDE_QUESTION_RE.search(query))


def _select_diverse_results(results: list[dict], limit: int = 6) -> list[dict]:
    if not results:
        return []

    def _path_weight(path: str) -> int:
        p = path.lower()
        if p.endswith("readme.md"):
            return 0
        if p.endswith(("package.json", "pyproject.toml", "requirements.txt", "go.mod", "cargo.toml")):
            return 1
        if p.endswith(("dockerfile", "docker-compose.yml", "docker-compose.yaml")):
            return 2
        if any(k in p for k in ("/main.", "/index.", "/app.", "/server.", "/cli.")):
            return 3
        if any(k in p for k in ("/src/", "/app/", "/lib/", "/core/", "/services/", "/components/")):
            return 4
        return 5

    ranked = sorted(
        enumerate(results),
        key=lambda x: (_path_weight(str(x[1].get("file_path") or "")), x[0]),
    )

    selected: list[dict] = []
    seen_paths: set[str] = set()
    seen_roots: set[str] = set()
    for _, item in ranked:
        path = str(item.get("file_path") or "")
        if not path or path in seen_paths:
            continue
        root = path.split("/", 1)[0]
        # Prefer root diversity but allow at most two per root.
        root_count = sum(1 for s in selected if str(s.get("file_path") or "").split("/", 1)[0] == root)
        if root in seen_roots and root_count >= 2:
            continue
        selected.append(item)
        seen_paths.add(path)
        seen_roots.add(root)
        if len(selected) >= limit:
            break

    if len(selected) < min(limit, len(results)):
        for item in results:
            if item in selected:
                continue
            selected.append(item)
            if len(selected) >= limit:
                break
    return selected


def _readme_contexts(db: Session, repo_id: UUID, limit: int = 2) -> list[dict]:
    """The opening of the root README: the best single source for what a project is, and one
    a "summarize this" query rarely retrieves on its own."""
    rows = (
        db.execute(
            select(CodeChunk)
            .where(CodeChunk.repo_id == repo_id, func.lower(CodeChunk.file_path).like("readme%"))
            .order_by(CodeChunk.file_path.asc(), CodeChunk.start_line.asc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [
        {
            "chunk_id": str(row.id),
            "file_path": row.file_path,
            "line_start": row.start_line,
            "line_end": row.end_line,
            "language": row.language,
            "content": row.content,
        }
        for row in rows
        if row.content.strip()
    ]


def plan_answer(db: Session, repo_id: UUID, query: str, results: list[dict]) -> dict:
    """Decide how to answer: a deterministic final string, or an LLM synthesis plan.

    Returns {"kind": "final", "text", "citations"} for the no-result and language branches, or
    {"kind": "llm", "contexts", "mode", "intent", "citations", "top", "refs"} when the answer
    should be synthesized (and streamed) from the model. Summary questions use the model's
    summary mode.
    """
    if _language_question(query):
        analysis = (
            db.execute(
                select(AnalysisResult)
                .where(AnalysisResult.repo_id == repo_id)
                .order_by(AnalysisResult.created_at.desc())
            )
            .scalars()
            .first()
        )
        answer = _language_answer(analysis.language_breakdown if analysis else None)
        if answer:
            # Whole-repository statistics, so there are no specific lines to cite.
            return {"kind": "final", "text": answer, "citations": {"citations": [], "no_citation": True}}

    if not results:
        return {
            "kind": "final",
            "text": "I could not find relevant indexed code context for that query.",
            "citations": {"citations": [], "no_citation": True},
        }

    top = results[: min(3, len(results))]
    diverse = _select_diverse_results(results, limit=min(MAX_CONTEXTS, len(results)))

    llm_contexts = []
    llm_candidates = diverse if diverse else top
    # Retrieval results carry only metadata, so load the chunk code the LLM must ground on.
    content_by_chunk = load_chunk_content(
        db,
        repo_id=repo_id,
        chunk_ids=[str(item.get("chunk_id")) for item in llm_candidates if item.get("chunk_id")],
    )
    for item in llm_candidates:
        chunk_id = str(item.get("chunk_id") or "")
        content = str(item.get("content") or content_by_chunk.get(chunk_id) or "")
        # A vector hit whose chunk row is gone (stale index) has no code to ground on.
        if not content.strip():
            continue
        llm_contexts.append(
            {
                "chunk_id": chunk_id,
                "file_path": item.get("file_path"),
                "line_start": item.get("start_line"),
                "line_end": item.get("end_line"),
                "language": item.get("language"),
                "content": content,
                "score": item.get("rerank_score") if item.get("rerank_score") is not None else item.get("score"),
            }
        )
    mode = "summary" if _summary_question(query) else "answer"
    if mode == "summary":
        readme = _readme_contexts(db, repo_id)
        readme_ids = {context["chunk_id"] for context in readme}
        llm_contexts = readme + [context for context in llm_contexts if context["chunk_id"] not in readme_ids]
    llm_contexts = llm_contexts[:MAX_CONTEXTS]

    # Every context the model sees is a citation, numbered as in the prompt so [n] in the answer maps back.
    formatted = [
        {
            **format_citation(
                chunk_id=context["chunk_id"],
                file_path=str(context["file_path"] or ""),
                line_start=context["line_start"],
                line_end=context["line_end"],
                score=context.get("score"),
            ),
            "ref": ref,
        }
        for ref, context in enumerate(llm_contexts, start=1)
    ]
    valid_citations = validate_citations_for_repo(db, repo_id=repo_id, citations=formatted)
    refs = [f"{item.get('file_path')}:{item.get('line_start') or 1}" for item in valid_citations] or ["no exact anchor"]
    citations = {
        "citations": valid_citations,
        "no_citation": len(valid_citations) == 0,
    }
    return {
        "kind": "llm",
        "contexts": llm_contexts,
        "mode": mode,
        "intent": detect_intent(query),
        "citations": citations,
        "top": top,
        "refs": refs,
    }


def snippet_fallback_text(db: Session, repo_id: UUID, top: list[dict], refs: list[str]) -> str:
    """Deterministic answer used when LLM synthesis is unavailable or empty."""
    snippets: list[str] = []
    content_by_chunk = load_chunk_content(
        db,
        repo_id=repo_id,
        chunk_ids=[str(item.get("chunk_id")) for item in top if item.get("chunk_id")],
    )
    for item in top:
        path = str(item.get("file_path") or "")
        line = item.get("start_line") or 1
        chunk_id = str(item.get("chunk_id") or "")
        raw_content = str(item.get("content") or content_by_chunk.get(chunk_id) or "").strip()
        preview = re.sub(r"\s+", " ", raw_content)[:120]
        if preview:
            snippets.append(f"{path}:{line} -> {preview}")
        else:
            snippets.append(f"{path}:{line}")

    if snippets:
        return "Based on indexed code context: " + " | ".join(snippets) + "."
    return "Relevant code context was found in: " + ", ".join(refs) + "."


def build_suggested_questions(db: Session, repo_id: UUID, limit: int) -> list[str]:
    file_rows = db.execute(
        select(CodeChunk.file_path)
        .where(CodeChunk.repo_id == repo_id)
        .distinct()
        .order_by(CodeChunk.file_path.asc())
        .limit(3)
    ).all()
    files = [row[0] for row in file_rows if row and row[0]]

    suggestions = [
        "What are the main architecture components in this repository?",
        "Where is authentication and token handling implemented?",
        "Which files show the core business logic flow?",
    ]
    for path in files:
        suggestions.append(f"Explain the responsibilities of `{path}`.")
    return suggestions[: max(1, min(limit, 10))]
