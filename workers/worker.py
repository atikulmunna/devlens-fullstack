import os
import time
from urllib.parse import urlparse

import redis


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
    redis_url = os.getenv("REDIS_URL", "redis://redis:6379/0")
    client = wait_for_redis(redis_url)
    print("Worker connected to Redis. Waiting for queue implementation...")

    while True:
        client.set("devlens:worker:heartbeat", int(time.time()), ex=30)
        time.sleep(10)


if __name__ == "__main__":
    main()
