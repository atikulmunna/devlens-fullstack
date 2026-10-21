"""The current analysis of a repository: the latest result, and the commit it read."""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisJob, AnalysisResult


def latest_analysis(db: Session, repo_id: UUID) -> AnalysisResult | None:
    return (
        db.execute(
            select(AnalysisResult)
            .where(AnalysisResult.repo_id == repo_id)
            .order_by(AnalysisResult.created_at.desc())
            .limit(1)
        )
        .scalars()
        .first()
    )


def analysis_commit_sha(db: Session, result: AnalysisResult | None) -> str | None:
    """The commit an analysis read; its indexed chunks, and so chat citations, come from it."""
    if result is None or result.job_id is None:
        return None
    job = db.get(AnalysisJob, result.job_id)
    return job.commit_sha if job else None
