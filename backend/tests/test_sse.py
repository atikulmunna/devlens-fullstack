import json

from app.api.sse import sse_event, stream_answer, stream_text
from app.services.chat_synthesizer import ChatSynthesisError, detect_intent


def _tokens(events: list[str]) -> str:
    return "".join(json.loads(event.split("data: ", 1)[1])["token"] for event in events)


def _drain(generator) -> tuple[list[str], str]:
    events = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value


def test_sse_event_format() -> None:
    assert sse_event("done", {"a": 1}) == 'event: done\ndata: {"a": 1}\n\n'


def test_stream_text_sends_words_as_deltas() -> None:
    assert _tokens(list(stream_text("two words"))) == "two words "


def test_stream_answer_forwards_model_tokens_and_returns_the_answer() -> None:
    events, answer = _drain(stream_answer(lambda: iter(["Hello ", "world"]), lambda: "unused", "label"))

    assert _tokens(events) == "Hello world"
    assert answer == "Hello world"


def test_stream_answer_falls_back_when_the_model_fails_before_any_token(caplog) -> None:
    def failing():
        raise ChatSynthesisError("provider down")

    events, answer = _drain(stream_answer(failing, lambda: "Fallback text", "Chat failed for s1"))

    assert answer == "Fallback text"
    assert _tokens(events) == "Fallback text "
    assert "Chat failed for s1: provider down" in caplog.text


def test_stream_answer_keeps_partial_text_when_the_model_fails_mid_stream() -> None:
    def partial():
        yield "Partial "
        raise ChatSynthesisError("dropped")

    events, answer = _drain(stream_answer(partial, lambda: "unused", "label"))

    assert answer == "Partial"
    assert _tokens(events) == "Partial "


def test_detect_intent_priority_and_default() -> None:
    assert detect_intent("Which module checks the auth token?") == "security"
    assert detect_intent("How do the components depend on each other?") == "architecture"
    assert detect_intent("Why does this commit break the callers?") == "debug"
    assert detect_intent("How do I install and start it?") == "setup"
    assert detect_intent("What does this repo do?") == "general"
