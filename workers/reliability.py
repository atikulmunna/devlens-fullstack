import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import text
from sqlalchemy.orm import Session

from config import settings


def is_retriable_error(stage: str, error_code: str) -> bool:
    if error_code.endswith("TIMEOUT"):
        return True
    if stage == "embedding" and error_code == "EMBED_UPSERT_FAILED":
        return True
    if stage == "parsing" and error_code in {"CLONE_FAILED", "CLONE_TIMEOUT"}:
        return True
    if error_code.startswith("UNEXPECTED_"):
        return True
    return False


def schedule_retry_or_dead_letter(
    db: Session,
    *,
    job_id: str,
    repo_id: str,
    stage: str,
    error_code: str,
    message: str,
    metadata: dict | None = None,
) -> None:
    row = db.execute(
        text(
            """
            SELECT retry_count
            FROM analysis_jobs
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {"job_id": job_id},
    ).mappings().first()

    retry_count = int((row or {}).get("retry_count") or 0)
    retriable = is_retriable_error(stage, error_code)
    max_attempts = max(0, settings.worker_retry_max_attempts)

    if retriable and retry_count < max_attempts:
        delay_seconds = settings.worker_retry_base_delay_seconds * (2 ** retry_count)
        next_retry_at = datetime.now(UTC) + timedelta(seconds=delay_seconds)
        db.execute(
            text(
                """
                UPDATE analysis_jobs
                SET status = :stage,
                    error_message = :error_message,
                    retry_count = :retry_count,
                    next_retry_at = :next_retry_at,
                    completed_at = NULL
                WHERE id = CAST(:job_id AS uuid)
                """
            ),
            {
                "job_id": job_id,
                "stage": stage,
                "retry_count": retry_count + 1,
                "next_retry_at": next_retry_at,
                "error_message": f"{error_code}: {message}",
            },
        )
        return

    now = datetime.now(UTC)
    db.execute(
        text(
            """
            UPDATE analysis_jobs
            SET status = 'failed',
                progress = 100,
                error_message = :error_message,
                completed_at = :completed_at,
                next_retry_at = NULL
            WHERE id = CAST(:job_id AS uuid)
            """
        ),
        {
            "job_id": job_id,
            "completed_at": now,
            "error_message": f"{error_code}: {message}",
        },
    )
    db.execute(
        text(
            """
            INSERT INTO dead_letter_jobs (
                id, job_id, repo_id, stage, error_code, error_message, attempt_count, metadata
            ) VALUES (
                gen_random_uuid(), CAST(:job_id AS uuid), CAST(:repo_id AS uuid), :stage, :error_code, :error_message, :attempt_count,
                CAST(:metadata AS jsonb)
            )
            """
        ),
        {
            "job_id": job_id,
            "repo_id": repo_id,
            "stage": stage,
            "error_code": error_code,
            "error_message": message,
            "attempt_count": retry_count,
            "metadata": json.dumps(metadata or {}),
        },
    )

