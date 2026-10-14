import time
from dataclasses import dataclass
from uuid import uuid4

import httpx
from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings
from embed_cache import embed_with_cache
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
    headers: dict[str, str] | None = None,
) -> dict | None:
    last_error: Exception | None = None

    for attempt in range(1, settings.embed_retry_attempts + 1):
        try:
            with httpx.Client(timeout=20.0) as client:
                response = client.request(method, url, json=json_body, headers=headers)

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


def ensure_collection(vector_size: int) -> None:
    url = f"{str(settings.qdrant_url).rstrip('/')}/collections/{settings.qdrant_collection}"
    headers = {'api-key': settings.qdrant_api_key} if settings.qdrant_api_key else None
    body = {
        'vectors': {'size': vector_size, 'distance': 'Cosine'}
    }

    # Detect an existing collection whose vector dimension no longer matches the
    # embedder's output (e.g. after switching embedding models). A mismatched
    # collection is dropped and recreated once; every repo must then be re-analyzed.
    existing = _request_with_retries('GET', url, allowed_statuses={404}, headers=headers)
    if existing:
        vectors_cfg = (
            existing.get('result', {})
            .get('config', {})
            .get('params', {})
            .get('vectors', {})
        )
        current_size = vectors_cfg.get('size') if isinstance(vectors_cfg, dict) else None
        if current_size == vector_size:
            return
        _request_with_retries('DELETE', url, allowed_statuses={404}, headers=headers)

    _request_with_retries('PUT', url, json_body=body, allowed_statuses={409}, headers=headers)


def prepare_collection(repo_id: str, first_vectors: list[list[float]]) -> None:
    """Size the collection from the model's actual output, then clear the repo's old points.

    A hand-set vector size drifted from the model twice; the first batch is the source of truth.
    """
    vector_size = len(first_vectors[0]) if first_vectors else 0
    if vector_size == 0:
        raise EmbedError('EMBED_EMPTY_VECTOR', 'Embedding model returned an empty vector')
    ensure_collection(vector_size)
    delete_repo_vectors(repo_id)


def delete_repo_vectors(repo_id: str) -> None:
    # The parse stage replaces every chunk row, so the repo's existing points all reference
    # chunks that no longer exist; left in place they pile up and crowd out fresh results.
    url = f"{str(settings.qdrant_url).rstrip('/')}/collections/{settings.qdrant_collection}/points/delete?wait=true"
    headers = {'api-key': settings.qdrant_api_key} if settings.qdrant_api_key else None
    body = {'filter': {'must': [{'key': 'repo_id', 'match': {'value': repo_id}}]}}
    _request_with_retries('POST', url, json_body=body, headers=headers)


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
    headers = {'api-key': settings.qdrant_api_key} if settings.qdrant_api_key else None
    _request_with_retries('PUT', url, json_body={'points': points}, headers=headers)

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

            update_job_status(db, snapshot.job_id, 'embedding', 40)
            db.commit()

            batch_size = max(1, settings.embed_batch_size)

            for idx in range(0, len(chunks), batch_size):
                batch = chunks[idx: idx + batch_size]
                vectors = embed_with_cache(
                    [chunk.content for chunk in batch],
                    embed_texts,
                    model=settings.embed_model,
                    ttl_seconds=settings.embed_cache_ttl_seconds,
                )
                if idx == 0:
                    prepare_collection(snapshot.repo_id, vectors)
                batch_qdrant_ids = upsert_chunk_vectors(snapshot.repo_id, batch, vectors)
                # Stored per batch so the status stream can count indexed chunks while this runs.
                store_qdrant_point_ids(db, [chunk.id for chunk in batch], batch_qdrant_ids)

                progress = 40 + int(((idx + len(batch)) / len(chunks)) * 50)
                update_job_status(db, snapshot.job_id, 'embedding', min(progress, 95))
                db.commit()

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

