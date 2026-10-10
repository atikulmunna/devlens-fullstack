import json
from typing import Literal

import httpx

from app.config import settings
from app.services.openrouter import describe_error


class ChatSynthesisError(RuntimeError):
    pass


ChatIntent = Literal["general", "architecture", "setup", "debug", "security"]


def _system_prompt(mode: Literal["answer", "summary"], intent: ChatIntent) -> str:
    if mode == "summary":
        return (
            "You are a repository analyst. Use only retrieved context. "
            "Return exactly 4-6 concise bullets that cover: purpose, core modules, runtime flow, output formats. "
            "Do not include a 'Based on indexed code context' preface."
        )
    system_prompt = (
        "You answer developer questions strictly from retrieved repository code context. "
        "Do not invent facts. If evidence is weak, say so briefly."
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


def _build_request(
    prompt: str,
    mode: Literal["answer", "summary"],
    intent: ChatIntent,
) -> tuple[str, dict, dict]:
    if not settings.openrouter_api_key:
        raise ChatSynthesisError("OPENROUTER_API_KEY is not set")

    body = {
        "model": settings.llm_chat_model,
        "messages": [
            {"role": "system", "content": _system_prompt(mode, intent)},
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
):
    """Yield content tokens from OpenRouter's streaming chat completion (SSE)."""
    url, headers, body = _build_request(prompt, mode, intent)
    try:
        with httpx.Client(timeout=float(settings.llm_chat_timeout_seconds)) as client:
            with client.stream("POST", url, headers=headers, json=body) as response:
                if response.status_code != 200:
                    response.read()
                    raise ChatSynthesisError(f"OpenRouter returned {describe_error(response)}")
                for line in response.iter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[len("data:"):].strip()
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
    for idx, item in enumerate(contexts[:6], start=1):
        trimmed_contexts.append(
            {
                "rank": idx,
                "file_path": item.get("file_path"),
                "line_start": item.get("line_start"),
                "line_end": item.get("line_end"),
                "language": item.get("language"),
                "content": (item.get("content") or "")[:1200],
            }
        )

    prompt = (
        "Question:\n"
        f"{query.strip()}\n\n"
        "Retrieved code contexts (JSON):\n"
        f"{json.dumps(trimmed_contexts)}\n\n"
    )
    if mode == "summary":
        prompt += (
            "Provide a high-level repository summary in 4-6 bullets covering: "
            "purpose, core modules, runtime flow, and output formats. "
            "Ground every bullet in the provided evidence."
        )
    else:
        prompt += (
            "Write a concise answer in plain text grounded only in this evidence. "
            "Mention uncertainty if evidence is partial. Keep under 6 sentences."
        )
    return prompt


def synthesize_grounded_answer_stream(
    query: str,
    contexts: list[dict],
    mode: Literal["answer", "summary"] = "answer",
    intent: ChatIntent = "general",
):
    """Stream grounded-answer tokens from OpenRouter as they arrive.

    Every failure surfaces as ChatSynthesisError, so callers handle one error type: tokens
    already yielded stay delivered, and callers fall back to deterministic text when nothing
    was streamed.
    """
    if not contexts:
        raise ChatSynthesisError("No contexts provided for synthesis")

    prompt = _build_prompt(query, contexts, mode)
    emitted = False
    try:
        for piece in _iter_tokens(prompt, mode=mode, intent=intent):
            emitted = True
            yield piece
    except ChatSynthesisError:
        raise
    except Exception as exc:  # noqa: BLE001 - e.g. a malformed stream chunk
        raise ChatSynthesisError(f"OpenRouter stream failed: {exc}") from exc

    if not emitted:
        raise ChatSynthesisError("OpenRouter returned an empty stream")
