import time
from urllib.parse import urlparse

import redis

from config import settings
from analyze_worker import process_next_analyze_job
from db import SessionLocal
from embed_worker import process_next_embed_job
from parse_worker import process_next_parse_job
from telemetry import start_metrics_server


def wait_for_redis(redis_url: str, retries: int = 20, delay: int = 2) -> redis.Redis:
    parsed = urlparse(redis_url)
    client = redis.Redis(
        host=parsed.hostname,
        port=parsed.port or 6379,
        db=int((parsed.path or "/0").strip("/") or 0),
        decode_responses=True,
    )
    for _ in range(retries):
        try:
            client.ping()
            return client
        except redis.RedisError:
            time.sleep(delay)
    raise RuntimeError("Unable to connect to Redis")


def main() -> None:
    client = wait_for_redis(settings.redis_url)
    start_metrics_server(settings.worker_metrics_port)
    print(f"Worker connected to Redis in {settings.env} mode. Parse+embed+analyze worker started.")

    while True:
        client.set("devlens:worker:heartbeat", int(time.time()), ex=30)
        db = SessionLocal()
        try:
            processed_parse = process_next_parse_job(db)
            processed_embed = False if processed_parse else process_next_embed_job(db)
            processed_analyze = False if (processed_parse or processed_embed) else process_next_analyze_job(db)
        finally:
            db.close()

        if not processed_parse and not processed_embed and not processed_analyze:
            time.sleep(2)
            continue

        time.sleep(10)


if __name__ == "__main__":
    main()
