import re
import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from parse_worker import update_job_status
from reliability import schedule_retry_or_dead_letter
from telemetry import record_stage_duration, trace_span
from config import settings


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


@dataclass
class ChunkRecord:
    file_path: str
    start_line: int | None
    end_line: int | None
    content: str
    language: str | None


def fetch_next_analyze_job(db: Session) -> AnalyzeSnapshot | None:
    row = db.execute(
        text(
            """
            SELECT j.id::text AS job_id,
                   j.repo_id::text AS repo_id,
                   r.full_name,
                   r.default_branch
            FROM analysis_jobs j
            JOIN repositories r ON r.id = j.repo_id
            WHERE j.status = 'analyzing'
              AND (j.next_retry_at IS NULL OR j.next_retry_at <= NOW())
            ORDER BY j.created_at ASC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        return None

    return AnalyzeSnapshot(
        repo_id=row['repo_id'],
        job_id=row['job_id'],
        full_name=row['full_name'],
        default_branch=row['default_branch'] or 'main',
    )


def load_repo_chunks(db: Session, repo_id: str) -> list[ChunkRecord]:
    rows = db.execute(
        text(
            """
            SELECT file_path, start_line, end_line, content, language
            FROM code_chunks
            WHERE repo_id = CAST(:repo_id AS uuid)
            ORDER BY created_at ASC
            """
        ),
        {'repo_id': repo_id},
    ).mappings().all()

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
    return {lang: round((size / total_size) * 100, 2) for lang, size in sorted(totals.items(), key=lambda kv: kv[1], reverse=True)}


def detect_tech_debt(chunks: list[ChunkRecord]) -> dict:
    long_functions = []
    todo_count = 0
    source_files = set()
    test_files = set()

    for chunk in chunks:
        path = chunk.file_path
        lower_path = path.lower()
        source_files.add(path)
        if '/tests/' in lower_path or lower_path.startswith('tests/') or 'test_' in lower_path:
            test_files.add(path)

        span = None
        if chunk.start_line is not None and chunk.end_line is not None:
            span = chunk.end_line - chunk.start_line + 1

        if span and span > 50:
            long_functions.append(
                {
                    'file': path,
                    'line': chunk.start_line,
                    'length': span,
                }
            )

        todo_count += len(re.findall(r'(?i)\b(TODO|FIXME)\b', chunk.content))

    missing_tests = []
    if not test_files:
        missing_tests = sorted(list(source_files))[:20]

    return {
        'long_functions': long_functions[:50],
        'todo_count': todo_count,
        'missing_tests': missing_tests,
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
    except Exception:
        return {'top_contributors': [], 'error': 'github_unreachable'}


def build_architecture_summary(snapshot: AnalyzeSnapshot, lang_breakdown: dict, chunks: list[ChunkRecord]) -> str:
    top_lang = next(iter(lang_breakdown.keys()), 'unknown')
    unique_paths = sorted({chunk.file_path for chunk in chunks})
    sample_paths = ', '.join(unique_paths[:5]) if unique_paths else 'no source files discovered'

    return (
        f"Repository {snapshot.full_name} (branch {snapshot.default_branch}) is primarily {top_lang}. "
        f"The parse/index stage identified {len(unique_paths)} source files and {len(chunks)} chunks. "
        f"Representative paths include: {sample_paths}. "
        "This summary is generated from structural chunk metadata and should be refined with LLM synthesis in later stages."
    )


def generate_architecture_summary(snapshot: AnalyzeSnapshot, lang_breakdown: dict, chunks: list[ChunkRecord]) -> str:
    fallback = build_architecture_summary(snapshot, lang_breakdown, chunks)
    if not settings.openrouter_api_key:
        return fallback

    top_paths = sorted({chunk.file_path for chunk in chunks})[:25]
    prompt = (
        f"Repository: {snapshot.full_name}\n"
        f"Branch: {snapshot.default_branch}\n"
        f"Files discovered: {len(top_paths)} sampled from {len(chunks)} chunks\n"
        f"Language breakdown: {json.dumps(lang_breakdown)}\n"
        f"Representative files: {', '.join(top_paths) if top_paths else 'none'}\n\n"
        "Write a concise architecture summary (3-5 sentences) for an engineering dashboard. "
        "Mention major layers/modules and likely responsibilities. "
        "Do not invent files or technologies not reflected in the provided metadata."
    )

    try:
        base = str(settings.openrouter_base_url).rstrip("/")
        url = f"{base}/chat/completions"
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
            "max_tokens": 220,
        }

        with httpx.Client(timeout=float(settings.llm_summary_timeout_seconds)) as client:
            response = client.post(url, headers=headers, json=body)

        if response.status_code != 200:
            return fallback

        data = response.json()
        text = (
            data.get("choices", [{}])[0]
            .get("message", {})
            .get("content", "")
            .strip()
        )
        return text if text else fallback
    except Exception:
        return fallback


def compute_quality_score(tech_debt: dict, file_tree: dict) -> int:
    score = 100

    todo_penalty = min(30, int(tech_debt.get('todo_count', 0)))
    score -= todo_penalty

    long_fn_penalty = min(30, len(tech_debt.get('long_functions', [])) * 2)
    score -= long_fn_penalty

    if tech_debt.get('missing_tests'):
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
    existing = db.execute(
        text('SELECT id::text FROM analysis_results WHERE job_id = CAST(:job_id AS uuid) LIMIT 1'),
        {'job_id': snapshot.job_id},
    ).mappings().first()

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
            tech_debt = detect_tech_debt(chunks)
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

