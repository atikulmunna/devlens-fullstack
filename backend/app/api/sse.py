"""Server-Sent Events formatting and the shared "stream the model, else fall back" answer stream."""

import json
import logging
from collections.abc import Callable, Generator, Iterable, Iterator

from app.services.chat_synthesizer import ChatSynthesisError

logger = logging.getLogger(__name__)

SSE_HEADERS = {"Cache-Control": "no-cache", "Connection": "keep-alive"}


def sse_event(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_text(text: str) -> Iterator[str]:
    """Fixed text as delta events, a word at a time, so the client renders it like model output."""
    for word in text.split(" "):
        yield sse_event("delta", {"token": word + " "})


def stream_answer(
    start: Callable[[], Iterable[str]], fallback: Callable[[], str], failure_label: str
) -> Generator[str, None, str]:
    """Delta events for model tokens as they arrive; returns the full answer text.

    `start()` begins the model stream inside the error handling, so a failure on the first call
    is handled like one mid-stream. A failure mid-stream keeps what was already delivered. When the
    model streamed nothing, `fallback()` supplies the answer instead.
    """
    parts: list[str] = []
    try:
        for piece in start():
            parts.append(piece)
            yield sse_event("delta", {"token": piece})
    except ChatSynthesisError as exc:
        logger.warning("%s: %s", failure_label, exc)

    answer = "".join(parts).strip()
    if answer:
        return answer
    answer = fallback()
    yield from stream_text(answer)
    return answer
