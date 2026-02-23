import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from reliability import schedule_retry_or_dead_letter
from telemetry import record_stage_duration, trace_span


SKIP_DIRS = {'.git', 'node_modules', '.venv', 'venv', 'dist', 'build', '__pycache__'}
ALLOWED_EXTENSIONS = {
    '.py', '.js', '.ts', '.tsx', '.jsx', '.go', '.java', '.cpp', '.c', '.h', '.hpp', '.rs', '.php', '.rb', '.cs',
}


class ParseError(RuntimeError):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class RepoSnapshot:
    repo_id: str
    job_id: str
    github_url: str
    commit_sha: str


def _run(cmd: list[str], cwd: str | None = None, timeout: int | None = None) -> None:
    try:
        subprocess.run(cmd, cwd=cwd, check=True, timeout=timeout, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except subprocess.TimeoutExpired as exc:
        raise ParseError('CLONE_TIMEOUT', 'Repository clone timed out') from exc
    except subprocess.CalledProcessError as exc:
        raise ParseError('CLONE_FAILED', f'Command failed: {exc.stderr.decode(errors="ignore")[:300]}') from exc


def clone_repo(github_url: str, commit_sha: str) -> str:
    temp_dir = tempfile.mkdtemp(prefix='devlens-parse-')
    _run(['git', 'clone', '--depth', '1', github_url, temp_dir], timeout=settings.parse_clone_timeout_seconds)
    _run(['git', 'fetch', '--depth', '1', 'origin', commit_sha], cwd=temp_dir, timeout=settings.parse_clone_timeout_seconds)
    _run(['git', 'checkout', commit_sha], cwd=temp_dir, timeout=settings.parse_clone_timeout_seconds)
    return temp_dir


def iter_source_files(root: str) -> Iterable[Path]:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for filename in files:
            path = Path(current) / filename
            if path.suffix.lower() in ALLOWED_EXTENSIONS:
                yield path


def chunk_lines(content: str, chunk_lines: int, overlap_lines: int) -> list[tuple[int, int, str]]:
    lines = content.splitlines()
    if not lines:
        return []

    if chunk_lines <= overlap_lines:
        raise ParseError('INVALID_CHUNK_CONFIG', 'Chunk size must be greater than overlap size')

    chunks: list[tuple[int, int, str]] = []
    start = 0
    while start < len(lines):
        end = min(start + chunk_lines, len(lines))
        chunk_content = '\n'.join(lines[start:end])
        chunks.append((start + 1, end, chunk_content))
        if end == len(lines):
            break
        start = end - overlap_lines

    return chunks


def update_job_status(db: Session, job_id: str, status: str, progress: int, error_message: str | None = None) -> None:
    db.execute(
        text(
            """
            UPDATE analysis_jobs
            SET status = :status,
                progress = :progress,
                error_message = :error_message,
                next_retry_at = NULL
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {
            'job_id': job_id,
            'status': status,
            'progress': progress,
            'error_message': error_message,
        },
    )


def fetch_next_parse_job(db: Session) -> RepoSnapshot | None:
    row = db.execute(
        text(
            """
            SELECT j.id::text AS job_id,
                   j.repo_id::text AS repo_id,
                   j.commit_sha,
                   r.github_url
            FROM analysis_jobs j
            JOIN repositories r ON r.id = j.repo_id
            WHERE j.status IN ('queued', 'parsing')
              AND (j.next_retry_at IS NULL OR j.next_retry_at <= NOW())
            ORDER BY j.created_at ASC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        return None

    return RepoSnapshot(
        repo_id=row['repo_id'],
        job_id=row['job_id'],
        github_url=row['github_url'],
        commit_sha=row['commit_sha'],
    )


def store_chunks(db: Session, repo_id: str, chunks: list[dict]) -> None:
    db.execute(text('DELETE FROM code_chunks WHERE repo_id = CAST(:repo_id AS uuid)'), {'repo_id': repo_id})

    for chunk in chunks:
        db.execute(
            text(
                """
                INSERT INTO code_chunks (id, repo_id, file_path, start_line, end_line, content, language, qdrant_point_id, fts)
                VALUES (
                    CAST(:id AS uuid),
                    CAST(:repo_id AS uuid),
                    :file_path,
                    :start_line,
                    :end_line,
                    :content,
                    :language,
                    NULL,
                    to_tsvector('english', coalesce(:file_path, '') || ' ' || coalesce(:content, ''))
                )
                """
            ),
            chunk,
        )


def parse_job(db: Session, snapshot: RepoSnapshot) -> None:
    started = time.perf_counter()
    update_job_status(db, snapshot.job_id, 'parsing', 10)
    db.commit()

    repo_path = None
    try:
        with trace_span("worker.parse", trace_id=snapshot.job_id, repo_id=snapshot.repo_id):
            repo_path = clone_repo(snapshot.github_url, snapshot.commit_sha)
            update_job_status(db, snapshot.job_id, 'parsing', 30)
            db.commit()

            files = list(iter_source_files(repo_path))
            if len(files) > settings.parse_max_files:
                raise ParseError('FILE_LIMIT_EXCEEDED', f'Repo has {len(files)} source files; limit is {settings.parse_max_files}')

            chunks: list[dict] = []
            for file_path in files:
                rel = str(file_path.relative_to(repo_path)).replace('\\', '/')
                language = file_path.suffix.lstrip('.').lower()

                with file_path.open('r', encoding='utf-8', errors='ignore') as fh:
                    content = fh.read()

                for start_line, end_line, chunk_content in chunk_lines(
                    content,
                    settings.parse_chunk_lines,
                    settings.parse_chunk_overlap_lines,
                ):
                    chunks.append(
                        {
                            'id': str(uuid4()),
                            'repo_id': snapshot.repo_id,
                            'file_path': rel,
                            'start_line': start_line,
                            'end_line': end_line,
                            'content': chunk_content,
                            'language': language,
                        }
                    )
                    if len(chunks) > settings.parse_max_chunks:
                        raise ParseError('CHUNK_LIMIT_EXCEEDED', f'Chunk limit exceeded: {settings.parse_max_chunks}')

            update_job_status(db, snapshot.job_id, 'parsing', 80)
            store_chunks(db, snapshot.repo_id, chunks)
            update_job_status(db, snapshot.job_id, 'embedding', 100)
            db.commit()
            record_stage_duration("parsing", "success", time.perf_counter() - started)

    except ParseError as exc:
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='parsing',
            error_code=exc.code,
            message=str(exc),
            metadata={'github_url': snapshot.github_url, 'commit_sha': snapshot.commit_sha},
        )
        db.commit()
        record_stage_duration("parsing", "error", time.perf_counter() - started)
    except Exception as exc:  # pragma: no cover - safety fallback
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='parsing',
            error_code='UNEXPECTED_PARSE_ERROR',
            message=str(exc),
            metadata={'github_url': snapshot.github_url, 'commit_sha': snapshot.commit_sha},
        )
        db.commit()
        record_stage_duration("parsing", "error", time.perf_counter() - started)
    finally:
        if repo_path and os.path.isdir(repo_path):
            shutil.rmtree(repo_path, ignore_errors=True)


def process_next_parse_job(db: Session) -> bool:
    snapshot = fetch_next_parse_job(db)
    if not snapshot:
        return False

    parse_job(db, snapshot)
    return True
