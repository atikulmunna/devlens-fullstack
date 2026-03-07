import json
from typing import Literal

import httpx

from app.config import settings


class ChatSynthesisError(RuntimeError):
    pass


ChatIntent = Literal["general", "architecture", "setup", "debug", "security"]


def _provider_chain() -> list[str]:
    primary = (settings.llm_primary_provider or "openrouter").strip().lower()
    fallback = (settings.llm_fallback_provider or "").strip().lower()
    if fallback and fallback == primary:
        fallback = ""
    return [primary] + ([fallback] if fallback else [])


def _provider_config(provider: str) -> tuple[str, str, str, float]:
    p = provider.strip().lower()
    if p == "openrouter":
        return (
            str(settings.openrouter_base_url).rstrip("/"),
            settings.openrouter_api_key,
            settings.llm_chat_model,
            float(settings.llm_primary_timeout_seconds),
        )
    if p == "groq":
        return (
            str(settings.groq_base_url).rstrip("/"),
            settings.groq_api_key,
            settings.llm_fallback_model or settings.llm_chat_model,
            float(settings.llm_fallback_timeout_seconds),
        )
    raise ChatSynthesisError(f"Unsupported LLM provider: {provider}")


def _call_provider(
    provider: str,
    prompt: str,
    mode: Literal["answer", "summary"],
    intent: ChatIntent,
) -> str:
    base_url, api_key, model, timeout = _provider_config(provider)
    if not api_key:
        raise ChatSynthesisError(f"Missing API key for provider: {provider}")

    system_prompt = (
        "You answer developer questions strictly from retrieved repository code context. "
        "Do not invent facts. If evidence is weak, say so briefly."
    )
    if mode == "summary":
        system_prompt = (
            "You are a repository analyst. Use only retrieved context. "
            "Return exactly 4-6 concise bullets that cover: purpose, core modules, runtime flow, output formats. "
            "Do not include a 'Based on indexed code context' preface."
        )
    elif intent == "architecture":
        system_prompt += " Focus on components, boundaries, and data/control flow between modules."
    elif intent == "setup":
        system_prompt += " Focus on practical setup/run steps, required files, and commands inferred from context."
    elif intent == "debug":
        system_prompt += " Focus on likely failure points, diagnostics, and concrete next checks from the cited files."
    elif intent == "security":
        system_prompt += " Focus on auth, token handling, secrets, permissions, and security-sensitive flows."

    body = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": system_prompt,
            },
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
        "max_tokens": 260,
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.post(f"{base_url}/chat/completions", headers=headers, json=body)
    except httpx.TimeoutException as exc:
        raise ChatSynthesisError(f"{provider} timeout: {exc}") from exc
    except httpx.TransportError as exc:
        raise ChatSynthesisError(f"{provider} transport error: {exc}") from exc

    if response.status_code != 200:
        raise ChatSynthesisError(f"{provider} returned status {response.status_code}")

    payload = response.json()
    text = (
        payload.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
        .strip()
    )
    if not text:
        raise ChatSynthesisError(f"{provider} returned empty response")
    return text


def synthesize_grounded_answer(
    query: str,
    contexts: list[dict],
    mode: Literal["answer", "summary"] = "answer",
    intent: ChatIntent = "general",
) -> str:
    if not contexts:
        raise ChatSynthesisError("No contexts provided for synthesis")

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

    last_error: Exception | None = None
    for provider in _provider_chain():
        try:
            return _call_provider(provider, prompt, mode=mode, intent=intent)
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            continue

    raise ChatSynthesisError(str(last_error) if last_error else "No provider available")
