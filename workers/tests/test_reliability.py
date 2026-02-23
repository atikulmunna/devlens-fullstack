import reliability


class FakeResult:
    def __init__(self, retry_count: int) -> None:
        self._retry_count = retry_count

    def mappings(self):
        return self

    def first(self):
        return {"retry_count": self._retry_count}


class FakeSession:
    def __init__(self, retry_count: int) -> None:
        self.retry_count = retry_count
        self.events = []

    def execute(self, statement, params=None):
        sql = str(statement)
        self.events.append((sql, params))
        if "SELECT retry_count" in sql:
            return FakeResult(self.retry_count)
        return self


def test_schedule_retry_for_retriable_error(monkeypatch) -> None:
    fake_db = FakeSession(retry_count=0)
    monkeypatch.setattr(reliability.settings, "worker_retry_max_attempts", 3)
    monkeypatch.setattr(reliability.settings, "worker_retry_base_delay_seconds", 10)

    reliability.schedule_retry_or_dead_letter(
        fake_db,
        job_id="00000000-0000-0000-0000-000000000091",
        repo_id="00000000-0000-0000-0000-000000000092",
        stage="embedding",
        error_code="EMBED_UPSERT_FAILED",
        message="temporary",
    )

    sql_calls = [sql for sql, _ in fake_db.events]
    assert any("UPDATE analysis_jobs" in sql and "retry_count" in sql for sql in sql_calls)
    assert all("INSERT INTO dead_letter_jobs" not in sql for sql in sql_calls)


def test_move_to_dead_letter_after_retry_limit(monkeypatch) -> None:
    fake_db = FakeSession(retry_count=3)
    monkeypatch.setattr(reliability.settings, "worker_retry_max_attempts", 3)
    monkeypatch.setattr(reliability.settings, "worker_retry_base_delay_seconds", 10)

    reliability.schedule_retry_or_dead_letter(
        fake_db,
        job_id="00000000-0000-0000-0000-000000000093",
        repo_id="00000000-0000-0000-0000-000000000094",
        stage="parsing",
        error_code="CLONE_TIMEOUT",
        message="still failing",
    )

    sql_calls = [sql for sql, _ in fake_db.events]
    assert any("UPDATE analysis_jobs" in sql and "status = 'failed'" in sql for sql in sql_calls)
    assert any("INSERT INTO dead_letter_jobs" in sql for sql in sql_calls)
