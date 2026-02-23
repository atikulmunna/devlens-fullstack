import hashlib
from typing import Iterable

from config import settings


# Deterministic local embedder for development/testing. Replace with sentence-transformers in model-serving phase.
def embed_text(text: str, size: int | None = None) -> list[float]:
    target = size or settings.embed_vector_size
    result: list[float] = []
    counter = 0

    while len(result) < target:
        digest = hashlib.sha256(f"{text}|{counter}".encode('utf-8')).digest()
        counter += 1

        for i in range(0, len(digest), 4):
            if len(result) >= target:
                break
            chunk = digest[i:i + 4]
            value = int.from_bytes(chunk, byteorder='big', signed=False)
            # Scale to [-1, 1].
            result.append((value / 2147483647.5) - 1.0)

    return result


def embed_texts(texts: Iterable[str], size: int | None = None) -> list[list[float]]:
    return [embed_text(text, size=size) for text in texts]
