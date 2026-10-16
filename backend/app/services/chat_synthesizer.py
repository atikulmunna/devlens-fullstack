import json
from typing import Literal

import httpx

from app.config import settings
from app.services.citations import CITATION_MARKER
from app.services.openrouter import describe_error


class ChatSynthesisError(RuntimeError):
    pass


ChatIntent = Literal["general", "architecture", "setup", "debug", "security"]

# Checked in order; the first group with a matching word wins. Security words are the most
# specific, setup words ("run", "start", "env") the most generic.
INTENT_WORDS: list[tuple[ChatIntent, tuple[str, ...]]] = [
    (
        "security",
        (
            "security",
            "auth",
            "token",
            "permission",
            "secret",
            "csrf",
            "oauth",
            "vulnerab",
            "credential",
            "password",
            "risk",
        ),
    ),
    ("architecture", ("architecture", "design", "structure", "component", "module", "flow", "dependency", "coupling")),
    (
        "debug",
        (
            "bug",
            "error",
            "fail",
            "exception",
            "debug",
            "issue",
            "fix",
            "broke",
            "break",
            "regress",
            "impact",
            "affect",
            "caller",
        ),
    ),
    ("setup", ("setup", "install", "run", "start", "configure", "env", "docker", "deploy")),
]

# How many retrieved contexts the model sees; each one is numbered and citable as [n].
MAX_CONTEXTS = 6
# Earlier turns sent with a follow-up question, each capped so a long answer cannot crowd out the code.
HISTORY_CHARS = 1500
CITE_INSTRUCTION = (
    "Cite the contexts you rely on inline by their ref number in square brackets, like [2]. "
    "Use only the ref numbers listed."
)


def detect_intent(question: str) -> ChatIntent:
    """The focus a question needs, which picks the system prompt emphasis and the answer length."""
    q = question.lower()
    return next((intent for intent, words in INTENT_WORDS if any(word in q for word in words)), "general")


def _system_prompt(mode: Literal["answer", "summary"], intent: ChatIntent) -> str:
    if mode == "summary":
        return (
            "You are a repository analyst. Use only the retrieved context. "
            "Return 4 to 6 concise bullets that cover: what the project is for, its main components, "
            "how a request or run flows through them, and how it is used or run. "
            "Skip any point the context does not support instead of guessing."
        )
    system_prompt = (
        "You answer developer questions strictly from retrieved repository code context. "
        "Do not invent facts. If evidence is weak, say so briefly. "
        "Earlier turns of the conversation are there to resolve follow-up questions; "
        "ground the answer in the retrieved contexts."
    )
    if intent == "architecture":
        system_prompt += " Focus on components, boundaries, and data/control flow between modules."
    elif intent == "setup":
        system_prompt += " Focus on practical setup/run steps, required files, and commands inferred from context."
    elif intent == "debug":
        system_prompt += " Focus on likely failure points, diagnostics, and concrete next checks from the cited files."
    elif intent == "security":
        system_prompt += " Focus on auth, token handling, secrets, permissions, and security-sensitive flows."
    return system_prompt


def _max_tokens(mode: Literal["answer", "summary"], intent: ChatIntent) -> int:
    # Architecture/debug answers and summaries need more room than a short factual reply.
    if mode == "summary":
        return 320
    if intent in ("architecture", "debug"):
        return 512
    if intent in ("setup", "security"):
        return 400
    return 260


def _history_messages(history: list[dict]) -> list[dict]:
    """Earlier turns as chat messages. Their [n] markers pointed at that turn's contexts, so they
    are removed rather than left to clash with this turn's numbering."""
    messages = []
    for turn in history:
        content = CITATION_MARKER.sub("", str(turn.get("content") or "")).strip()
        if turn.get("role") in ("user", "assistant") and content:
            messages.append({"role": turn["role"], "content": content[:HISTORY_CHARS]})
    return messages


def _build_request(
    prompt: str,
    mode: Literal["answer", "summary"],
    intent: ChatIntent,
    history: list[dict],
) -> tuple[str, dict, dict]:
    if not settings.openrouter_api_key:
        raise ChatSynthesisError("OPENROUTER_API_KEY is not set")

    body = {
        "model": settings.llm_chat_model,
        "messages": [
            {"role": "system", "content": _system_prompt(mode, intent)},
            *_history_messages(history),
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": _max_tokens(mode, intent),
        "stream": True,
    }
    headers = {"Authorization": f"Bearer {settings.openrouter_api_key}", "Content-Type": "application/json"}
    return f"{str(settings.openrouter_base_url).rstrip('/')}/chat/completions", headers, body


def _iter_tokens(
    prompt: str,
    mode: Literal["answer", "summary"],
    intent: ChatIntent,
    history: list[dict],
):
    """Yield content tokens from OpenRouter's streaming chat completion (SSE)."""
    url, headers, body = _build_request(prompt, mode, intent, history)
    try:
        with httpx.Client(timeout=float(settings.llm_chat_timeout_seconds)) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    response.read()
                    raise ChatSynthesisError(f"OpenRouter returned {describe_error(response)}")
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:") :].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        continue
                    delta = (chunk.get("choices", [{}])[0] or {}).get("delta", {}) or {}
                    piece = delta.get("content")
                    if piece:
                        yield piece
    except httpx.TimeoutException as exc:
        raise ChatSynthesisError(f"OpenRouter timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise ChatSynthesisError(f"OpenRouter transport error: {exc}") from exc


def _build_prompt(query: str, contexts: list[dict], mode: Literal["answer", "summary"]) -> str:
    trimmed_contexts = []
    for idx, item in enumerate(contexts[:MAX_CONTEXTS], start=1):
        trimmed_contexts.append(
            {
                "ref": idx,
                "file_path": item.get("file_path"),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "language": item.get("language"),
                "content": (item.get("content") or "")[:1200],
            }
        )

    prompt = f"Question:\n{query.strip()}\n\nRetrieved code contexts (JSON):\n{json.dumps(trimmed_contexts)}\n\n"
    if mode == "summary":
        prompt += (
            "Summarize this repository in 4 to 6 bullets: what it is for, its main components, "
            "how a request or run flows through them, and how it is used or run. "
            "Ground every bullet in the provided evidence. "
            f"{CITE_INSTRUCTION}"
        )
    else:
        prompt += (
            "Write a concise answer in plain text grounded only in this evidence. "
            "Mention uncertainty if evidence is partial. Keep under 6 sentences. "
            f"{CITE_INSTRUCTION}"
        )
    return prompt


def synthesize_grounded_answer_stream(
    query: str,
    contexts: list[dict],
    mode: Literal["answer", "summary"] = "answer",
    intent: ChatIntent = "general",
    history: list[dict] | None = None,
):
    """Stream grounded-answer tokens from OpenRouter as they arrive.

    `history` is the session's earlier turns, oldest first, as {"role", "content"} dicts.

    Every failure surfaces as ChatSynthesisError, so callers handle one error type: tokens
    already yielded stay delivered, and callers fall back to deterministic text when nothing
    was streamed.
    """
    if not contexts:
        raise ChatSynthesisError("No contexts provided for synthesis")

    prompt = _build_prompt(query, contexts, mode)
    emitted = False
    try:
        for piece in _iter_tokens(prompt, mode=mode, intent=intent, history=history or []):
            emitted = True
            yield piece
    except ChatSynthesisError:
        raise
    except Exception as exc:  # noqa: BLE001 - e.g. a malformed stream chunk
        raise ChatSynthesisError(f"OpenRouter stream failed: {exc}") from exc

    if not emitted:
        raise ChatSynthesisError("OpenRouter returned an empty stream")
