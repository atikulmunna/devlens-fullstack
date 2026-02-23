import time
from dataclasses import dataclass
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from embeddings import embed_texts
from parse_worker import update_job_status
from reliability import schedule_retry_or_dead_letter
from telemetry import record_stage_duration, trace_span


class EmbedError(RuntimeError):
    code: str

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


@dataclass
class EmbedSnapshot:
    repo_id: str
    job_id: str


@dataclass
class ChunkRecord:
    id: str
    file_path: str
    start_line: int | None
    end_line: int | None
    content: str
    language: str | None


def fetch_next_embed_job(db: Session) -> EmbedSnapshot | None:
    row = db.execute(
        text(
            """
            SELECT id::text AS job_id, repo_id::text AS repo_id
            FROM analysis_jobs
            WHERE status = 'embedding'
              AND (next_retry_at IS NULL OR next_retry_at <= NOW())
            ORDER BY created_at ASC
            LIMIT 1
            """
        )
    ).mappings().first()

    if not row:
        return None

    return EmbedSnapshot(job_id=row['job_id'], repo_id=row['repo_id'])


def load_repo_chunks(db: Session, repo_id: str) -> list[ChunkRecord]:
    rows = db.execute(
        text(
            """
            SELECT id::text, file_path, start_line, end_line, content, language
            FROM code_chunks
            WHERE repo_id = CAST(:repo_id AS uuid)
            ORDER BY created_at ASC
            """
        ),
        {'repo_id': repo_id},
    ).mappings().all()

    return [
        ChunkRecord(
            id=row['id'],
            file_path=row['file_path'],
            start_line=row['start_line'],
            end_line=row['end_line'],
            content=row['content'],
            language=row['language'],
        )
        for row in rows
    ]


def _request_with_retries(
    method: str,
    url: str,
    *,
    json_body: dict | None = None,
    allowed_statuses: set[int] | None = None,
) -> dict | None:
    last_error: Exception | None = None

    for attempt in range(1, settings.embed_retry_attempts + 1):
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.request(method, url, json=json_body)

            if response.status_code >= 500:
                raise httpx.HTTPStatusError('Transient server error', request=response.request, response=response)

            if allowed_statuses and response.status_code in allowed_statuses:
                if response.content:
                    return response.json()
                return None

            if response.status_code >= 400:
                raise EmbedError('EMBED_UPSERT_FAILED', f'Qdrant request failed ({response.status_code}): {response.text[:200]}')

            if response.content:
                return response.json()
            return None
        except EmbedError:
            raise
        except Exception as exc:
            last_error = exc
            if attempt == settings.embed_retry_attempts:
                break
            time.sleep(0.5 * attempt)

    raise EmbedError('EMBED_UPSERT_FAILED', f'Qdrant request failed after retries: {last_error}')


def ensure_collection() -> None:
    url = f"{str(settings.qdrant_url).rstrip('/')}/collections/{settings.qdrant_collection}"
    body = {
        'vectors': {'size': settings.embed_vector_size, 'distance': 'Cosine'}
    }
    _request_with_retries('PUT', url, json_body=body, allowed_statuses={409})


def upsert_chunk_vectors(repo_id: str, chunks: list[ChunkRecord], vectors: list[list[float]]) -> list[str]:
    if len(chunks) != len(vectors):
        raise EmbedError('EMBED_VECTOR_MISMATCH', 'Chunks and vectors length mismatch')

    points = []
    qdrant_ids: list[str] = []
    for chunk, vector in zip(chunks, vectors):
        point_id = str(uuid4())
        qdrant_ids.append(point_id)
        points.append(
            {
                'id': point_id,
                'vector': vector,
                'payload': {
                    'repo_id': repo_id,
                    'file_path': chunk.file_path,
                    'start_line': chunk.start_line,
                    'end_line': chunk.end_line,
                    'language': chunk.language,
                    'chunk_id': chunk.id,
                },
            }
        )

    url = f"{str(settings.qdrant_url).rstrip('/')}/collections/{settings.qdrant_collection}/points?wait=true"
    _request_with_retries('PUT', url, json_body={'points': points})

    return qdrant_ids


def store_qdrant_point_ids(db: Session, chunk_ids: list[str], qdrant_ids: list[str]) -> None:
    for chunk_id, qdrant_id in zip(chunk_ids, qdrant_ids):
        db.execute(
            text(
                """
                UPDATE code_chunks
                SET qdrant_point_id = CAST(:qdrant_id AS uuid)
                WHERE id = CAST(:chunk_id AS uuid)
                """
            ),
            {
                'chunk_id': chunk_id,
                'qdrant_id': qdrant_id,
            },
        )


def embed_job(db: Session, snapshot: EmbedSnapshot) -> None:
    started = time.perf_counter()
    update_job_status(db, snapshot.job_id, 'embedding', 10)
    db.commit()

    try:
        with trace_span("worker.embed", trace_id=snapshot.job_id, repo_id=snapshot.repo_id):
            chunks = load_repo_chunks(db, snapshot.repo_id)
            if not chunks:
                raise EmbedError('NO_CHUNKS', 'No chunks available for embedding')

            ensure_collection()
            update_job_status(db, snapshot.job_id, 'embedding', 40)
            db.commit()

            qdrant_ids: list[str] = []
            chunk_ids: list[str] = []
            batch_size = max(1, settings.embed_batch_size)

            for idx in range(0, len(chunks), batch_size):
                batch = chunks[idx: idx + batch_size]
                vectors = embed_texts([chunk.content for chunk in batch], size=settings.embed_vector_size)
                batch_qdrant_ids = upsert_chunk_vectors(snapshot.repo_id, batch, vectors)

                chunk_ids.extend([chunk.id for chunk in batch])
                qdrant_ids.extend(batch_qdrant_ids)

                progress = 40 + int(((idx + len(batch)) / len(chunks)) * 50)
                update_job_status(db, snapshot.job_id, 'embedding', min(progress, 95))
                db.commit()

            store_qdrant_point_ids(db, chunk_ids, qdrant_ids)
            update_job_status(db, snapshot.job_id, 'analyzing', 100)
            db.commit()
            record_stage_duration("embedding", "success", time.perf_counter() - started)

    except EmbedError as exc:
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='embedding',
            error_code=exc.code,
            message=str(exc),
        )
        db.commit()
        record_stage_duration("embedding", "error", time.perf_counter() - started)
    except Exception as exc:  # pragma: no cover
        schedule_retry_or_dead_letter(
            db,
            job_id=snapshot.job_id,
            repo_id=snapshot.repo_id,
            stage='embedding',
            error_code='UNEXPECTED_EMBED_ERROR',
            message=str(exc),
        )
        db.commit()
        record_stage_duration("embedding", "error", time.perf_counter() - started)


def process_next_embed_job(db: Session) -> bool:
    snapshot = fetch_next_embed_job(db)
    if not snapshot:
        return False

    embed_job(db, snapshot)
    return True

