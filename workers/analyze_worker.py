import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from code_signals import LONG_FUNCTION_LINES, is_test_path
from config import settings
from openrouter import describe_error
from parse_worker import update_job_status
from reliability import schedule_retry_or_dead_letter
from telemetry import (
    record_llm_provider_attempt,
    record_stage_duration,
    trace_span,
)

logger = logging.getLogger(__name__)


class AnalyzeError(RuntimeError):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class AnalyzeSnapshot:
    repo_id: str
    job_id: str
    full_name: str
    default_branch: str
    # Measured by the parse stage from whole files (see code_signals.py); None for jobs parsed before that.
    code_signals: dict | None = None


@dataclass
class ChunkRecord:
    file_path: str
    start_line: int | None
    end_line: int | None
    content: str
    language: str | None


def fetch_next_analyze_job(db: Session) -> AnalyzeSnapshot | None:
    row = (
        db.execute(
            text(
                """
            SELECT j.id::text AS job_id,
                   j.repo_id::text AS repo_id,
                   r.full_name,
                   r.default_branch,
                   j.code_signals
            FROM analysis_jobs j
            JOIN repositories r ON r.id = j.repo_id
            WHERE j.status = 'analyzing'
              AND (j.next_retry_at IS NULL OR j.next_retry_at <= NOW())
            ORDER BY j.created_at ASC
            LIMIT 1
            """
            )
        )
        .mappings()
        .first()
    )

    if not row:
        return None

    return AnalyzeSnapshot(
        repo_id=row['repo_id'],
        job_id=row['job_id'],
        full_name=row['full_name'],
        default_branch=row['default_branch'] or 'main',
        code_signals=row['code_signals'],
    )


def load_repo_chunks(db: Session, repo_id: str) -> list[ChunkRecord]:
    rows = (
        db.execute(
            text(
                """
            SELECT file_path, start_line, end_line, content, language
            FROM code_chunks
            WHERE repo_id = CAST(:repo_id AS uuid)
            ORDER BY created_at ASC
            """
            ),
            {'repo_id': repo_id},
        )
        .mappings()
        .all()
    )

    return [
        ChunkRecord(
            file_path=row['file_path'],
            start_line=row['start_line'],
            end_line=row['end_line'],
            content=row['content'],
            language=row['language'],
        )
        for row in rows
    ]


def language_breakdown(chunks: list[ChunkRecord]) -> dict:
    totals: dict[str, int] = {}
    for chunk in chunks:
        lang = (chunk.language or 'unknown').lower()
        totals[lang] = totals.get(lang, 0) + len(chunk.content)

    total_size = sum(totals.values()) or 1
    return {
        lang: round((size / total_size) * 100, 2)
        for lang, size in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)
    }


def detect_tech_debt(chunks: list[ChunkRecord], code_signals: dict | None) -> dict:
    """Code health facts for the dashboard: long functions (longest first), TODO notes, test files."""
    signals = code_signals or {}
    long_functions = sorted(signals.get('long_functions', []), key=lambda item: item['length'], reverse=True)
    todo_files = signals.get('todo_files', {})
    test_files = {chunk.file_path for chunk in chunks if is_test_path(chunk.file_path)}
    return {
        'measured': code_signals is not None,
        'long_function_lines': LONG_FUNCTION_LINES,
        'long_function_count': len(long_functions),
        'long_functions': long_functions[:50],
        'todo_count': sum(todo_files.values()),
        'todo_file_count': len(todo_files),
        'test_file_count': len(test_files),
    }


def build_file_tree(chunks: list[ChunkRecord]) -> dict:
    metrics: dict[str, dict] = {}
    for chunk in chunks:
        path = chunk.file_path
        entry = metrics.setdefault(path, {'chunks': 0, 'lines': 0, 'language': chunk.language or 'unknown'})
        entry['chunks'] += 1
        if chunk.start_line and chunk.end_line:
            entry['lines'] += max(0, chunk.end_line - chunk.start_line + 1)

    return {'files': metrics}


def get_contributor_stats(full_name: str) -> dict:
    url = f'https://api.github.com/repos/{full_name}/contributors?per_page=10'
    headers = {
        'Accept': 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
    }

    try:
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, headers=headers)

        if response.status_code != 200:
            logger.warning('GitHub contributors request for %s returned status %s', full_name, response.status_code)
            return {'top_contributors': [], 'error': f'github_status_{response.status_code}'}

        data = response.json()
        return {
            'top_contributors': [
                {
                    'username': row.get('login'),
                    'commits': row.get('contributions', 0),
                }
                for row in data
            ]
        }
    except Exception as exc:
        logger.warning('GitHub contributors request for %s failed: %r', full_name, exc)
        return {'top_contributors': [], 'error': 'github_unreachable'}


def build_architecture_summary(snapshot: AnalyzeSnapshot, chunks: list[ChunkRecord]) -> str:
    """Shown on the dashboard when the model is unavailable: plain facts, no pipeline wording."""
    unique_paths = sorted({chunk.file_path for chunk in chunks})
    top_dirs = sorted({path.split('/', 1)[0] for path in unique_paths if '/' in path})[:6]
    files = f"{len(unique_paths)} indexed file{'' if len(unique_paths) == 1 else 's'}"
    where = f" across {', '.join(top_dirs)} and the repository root" if top_dirs else ""
    return f"{snapshot.full_name} has {files}{where}. A written summary was not generated for this analysis."


# Files that say what a project is and how it starts, in the order the summary prompt lists them.
SUMMARY_MANIFESTS = {
    'pyproject.toml',
    'setup.py',
    'package.json',
    'go.mod',
    'cargo.toml',
    'pom.xml',
    'build.gradle',
    'gemfile',
    'composer.json',
}
SUMMARY_ENTRYPOINTS = {
    '__main__.py',
    'main.py',
    'app.py',
    'server.py',
    'cli.py',
    'manage.py',
    'wsgi.py',
    'asgi.py',
    'main.go',
    'main.rs',
    'lib.rs',
    'index.ts',
    'index.js',
    'main.ts',
    'main.js',
    'server.ts',
    'server.js',
    'app.ts',
    'app.js',
}
SUMMARY_SOURCE_LIMIT = 6
SUMMARY_SOURCE_CHARS = 1500


def _summary_source_rank(path: str) -> int | None:
    """Lower is earlier: README, then manifests, then entrypoints and top-level packages. None skips."""
    lower = path.lower()
    parts = lower.split('/')
    name, depth = parts[-1], len(parts) - 1
    if any(part in ('test', 'tests', 'docs', 'examples', 'node_modules') for part in parts[:-1]):
        return None
    if depth == 0 and name.startswith('readme'):
        return 0
    if depth == 0 and name in SUMMARY_MANIFESTS:
        return 1
    if depth <= 2 and name in SUMMARY_ENTRYPOINTS:
        return 2 + depth
    if 1 <= depth <= 2 and name == '__init__.py':
        return 4 + depth
    return None


def select_summary_sources(chunks: list[ChunkRecord]) -> list[ChunkRecord]:
    """The opening chunk of the files that best explain the project, best first."""
    first_chunks: dict[str, ChunkRecord] = {}
    for chunk in chunks:
        if _summary_source_rank(chunk.file_path) is None or not chunk.content.strip():
            continue
        current = first_chunks.get(chunk.file_path)
        if current is None or (chunk.start_line or 0) < (current.start_line or 0):
            first_chunks[chunk.file_path] = chunk
    ranked = sorted(first_chunks.values(), key=lambda c: (_summary_source_rank(c.file_path), c.file_path))
    return ranked[:SUMMARY_SOURCE_LIMIT]


def _request_summary(prompt: str) -> str:
    """Ask OpenRouter for the summary; every failure becomes an AnalyzeError with a specific code."""
    if not settings.openrouter_api_key:
        raise AnalyzeError("LLM_PROVIDER_NO_API_KEY", "OPENROUTER_API_KEY is not set")

    url = f"{str(settings.openrouter_base_url).rstrip('/')}/chat/completions"
    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.llm_summary_model,
        "messages": [
            {"role": "system", "content": "You summarize repository architecture for developers."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 320,
    }

    try:
        with httpx.Client(timeout=float(settings.llm_summary_timeout_seconds)) as client:
            response = client.post(url, headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise AnalyzeError("LLM_PROVIDER_TIMEOUT", str(exc)) from exc
    except httpx.TransportError as exc:
        raise AnalyzeError("LLM_PROVIDER_TRANSPORT_ERROR", str(exc)) from exc
    except Exception as exc:
        raise AnalyzeError("LLM_PROVIDER_REQUEST_FAILED", str(exc)) from exc

    if response.status_code != 200:
        code = "LLM_PROVIDER_RATE_LIMITED" if response.status_code == 429 else "LLM_PROVIDER_HTTP_ERROR"
        raise AnalyzeError(code, f"OpenRouter returned {describe_error(response)}")

    data = response.json()
    text = data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
    if not text:
        raise AnalyzeError("LLM_PROVIDER_EMPTY_RESPONSE", "OpenRouter returned an empty summary")
    return text


def generate_architecture_summary(snapshot: AnalyzeSnapshot, lang_breakdown: dict, chunks: list[ChunkRecord]) -> str:
    fallback = build_architecture_summary(snapshot, chunks)

    all_paths = sorted({chunk.file_path for chunk in chunks})
    sources = "\n\n".join(
        f"--- {chunk.file_path} (from line {chunk.start_line or 1}) ---\n{chunk.content[:SUMMARY_SOURCE_CHARS]}"
        for chunk in select_summary_sources(chunks)
    )
    prompt = (
        f"Repository: {snapshot.full_name}\n"
        f"Language breakdown (percent of indexed size): {json.dumps(lang_breakdown)}\n"
        f"Files ({len(all_paths)}): {', '.join(all_paths[:60]) if all_paths else 'none'}\n\n"
        f"Key files (README, manifest, entry points):\n{sources or 'none found'}\n\n"
        "Write an architecture summary of 3 to 5 sentences for a developer new to this repository: "
        "what it does, its main modules and what each is responsible for, and how it is run or used. "
        "Use only what the files above show; do not invent files or technologies."
    )

    try:
        summary = _request_summary(prompt)
    except AnalyzeError as exc:
        error_code = exc.code
        logger.warning("Summary LLM call failed for %s (%s): %s", snapshot.full_name, exc.code, exc)
    except Exception as exc:
        error_code = "LLM_PROVIDER_UNEXPECTED_ERROR"
        logger.warning("Summary LLM call failed for %s: %r", snapshot.full_name, exc)
    else:
        record_llm_provider_attempt("openrouter", "success")
        return summary

    record_llm_provider_attempt("openrouter", "error", error_code)
    record_llm_provider_attempt("fallback_summary", "success", error_code)
    return fallback


def compute_quality_score(tech_debt: dict, file_tree: dict) -> int:
    score = 100

    todo_penalty = min(30, int(tech_debt.get('todo_count', 0)))
    score -= todo_penalty

    long_fn_penalty = min(30, int(tech_debt.get('long_function_count', 0)) * 2)
    score -= long_fn_penalty

    if not tech_debt.get('test_file_count'):
        score -= 20

    files = file_tree.get('files', {})
    has_readme = any(path.lower().endswith('readme.md') for path in files.keys())
    if has_readme:
        score += 5

    return max(0, min(100, score))


def store_analysis_result(
    db: Session,
    snapshot: AnalyzeSnapshot,
    summary: str,
    quality_score: int,
    lang_breakdown: dict,
    contributors: dict,
    tech_debt: dict,
    file_tree: dict,
) -> None:
    existing = (
        db.execute(
            text('SELECT id::text FROM analysis_results WHERE job_id = CAST(:job_id AS uuid) LIMIT 1'),
            {'job_id': snapshot.job_id},
        )
        .mappings()
        .first()
    )

    payload = {
        'repo_id': snapshot.repo_id,
        'job_id': snapshot.job_id,
        'summary': summary,
        'quality_score': quality_score,
        'language_breakdown': json.dumps(lang_breakdown),
        'contributor_stats': json.dumps(contributors),
        'tech_debt_flags': json.dumps(tech_debt),
        'file_tree': json.dumps(file_tree),
    }

    if existing:
        db.execute(
            text(
                """
                UPDATE analysis_results
                SET architecture_summary = :summary,
                    quality_score = :quality_score,
                    language_breakdown = CAST(:language_breakdown AS jsonb),
                    contributor_stats = CAST(:contributor_stats AS jsonb),
                    tech_debt_flags = CAST(:tech_debt_flags AS jsonb),
                    file_tree = CAST(:file_tree AS jsonb)
                WHERE id = CAST(:id AS uuid)
                """
            ),
            {**payload, 'id': existing['id']},
        )
    else:
        db.execute(
            text(
                """
                INSERT INTO analysis_results (
                    id, repo_id, job_id, architecture_summary, quality_score,
                    language_breakdown, contributor_stats, tech_debt_flags, file_tree
                ) VALUES (
                    CAST(:id AS uuid), CAST(:repo_id AS uuid), CAST(:job_id AS uuid), :summary, :quality_score,
                    CAST(:language_breakdown AS jsonb), CAST(:contributor_stats AS jsonb),
                    CAST(:tech_debt_flags AS jsonb), CAST(:file_tree AS jsonb)
                )
                """
            ),
            {**payload, 'id': str(uuid4())},
        )


def mark_job_done(db: Session, snapshot: AnalyzeSnapshot) -> None:
    now = datetime.now(UTC)
    db.execute(
        text(
            """
            UPDATE analysis_jobs
            SET status = 'done', progress = 100, completed_at = :completed_at, error_message = NULL
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {
            'job_id': snapshot.job_id,
            'completed_at': now,
        },
    )
    db.execute(
        text(
            """
            UPDATE repositories
            SET last_analyzed_at = :completed_at
            WHERE id = CAST(:repo_id AS uuid)
            """
        ),
        {
            'repo_id': snapshot.repo_id,
            'completed_at': now,
        },
    )


def analyze_job(db: Session, snapshot: AnalyzeSnapshot) -> None:
    started = time.perf_counter()
    update_job_status(db, snapshot.job_id, 'analyzing', 10)
    db.commit()

    try:
        with trace_span("worker.analyze", trace_id=snapshot.job_id, repo_id=snapshot.repo_id):
            chunks = load_repo_chunks(db, snapshot.repo_id)
            if not chunks:
                raise AnalyzeError('NO_CHUNKS', 'No chunks available for analysis')

            lang = language_breakdown(chunks)
            tech_debt = detect_tech_debt(chunks, snapshot.code_signals)
            file_tree = build_file_tree(chunks)
            contributors = get_contributor_stats(snapshot.full_name)
            summary = generate_architecture_summary(snapshot, lang, chunks)
            quality = compute_quality_score(tech_debt, file_tree)

            update_job_status(db, snapshot.job_id, 'analyzing', 80)
            store_analysis_result(db, snapshot, summary, quality, lang, contributors, tech_debt, file_tree)
            mark_job_done(db, snapshot)
            db.commit()
            record_stage_duration("analyzing", "success", time.perf_counter() - started)

    except AnalyzeError as exc:
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='analyzing',
            error_code=exc.code,
            message=str(exc),
        )
        db.commit()
        record_stage_duration("analyzing", "error", time.perf_counter() - started)
    except Exception as exc:  # pragma: no cover
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='analyzing',
            error_code='UNEXPECTED_ANALYZE_ERROR',
            message=str(exc),
        )
        db.commit()
        record_stage_duration("analyzing", "error", time.perf_counter() - started)


def process_next_analyze_job(db: Session) -> bool:
    snapshot = fetch_next_analyze_job(db)
    if not snapshot:
        return False

    analyze_job(db, snapshot)
    return True
