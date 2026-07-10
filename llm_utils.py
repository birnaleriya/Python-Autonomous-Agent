"""
llm_utils.py — Ollama HTTP helpers with JSON retry logic.
"""
from __future__ import annotations

import json
import re
import logging
from typing import Any

import httpx

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "llama3"
TIMEOUT = 300.0

logger = logging.getLogger(__name__)


def call_llm(prompt: str, system: str = "", model: str = DEFAULT_MODEL) -> str:
    """Send a prompt to Ollama and return the full response text."""
    payload: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "stream": False,
    }
    if system:
        payload["system"] = system

    try:
        response = httpx.post(OLLAMA_URL, json=payload, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()["response"].strip()
    except httpx.TimeoutException as exc:
        raise RuntimeError("LLM request timed out") from exc
    except httpx.HTTPStatusError as exc:
        raise RuntimeError(f"LLM HTTP error: {exc.response.status_code}") from exc


def _extract_json(text: str) -> Any:
    """Extract the first JSON object or array from a string."""
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost {...} or [...]
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        end = text.rfind(end_char)
        if start != -1 and end != -1 and end > start:
            try:
                return json.loads(text[start:end + 1])
            except json.JSONDecodeError:
                pass

    # Strip markdown code fences and retry
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Could not extract JSON from LLM response: {text[:300]}") from exc


def call_llm_json(
    prompt: str,
    system: str = "",
    model: str = DEFAULT_MODEL,
    retries: int = 2,
) -> Any:
    """
    Call the LLM and parse the response as JSON.
    On failure, retries with a stricter system prompt that demands raw JSON only.
    """
    strict_suffix = (
        "\n\nCRITICAL: Your entire response MUST be valid JSON only. "
        "No prose, no markdown fences, no explanation — raw JSON exclusively."
    )

    for attempt in range(retries + 1):
        effective_system = system if attempt == 0 else system + strict_suffix
        try:
            raw = call_llm(prompt, system=effective_system, model=model)
            return _extract_json(raw)
        except (ValueError, RuntimeError) as exc:
            logger.warning("JSON parse attempt %d/%d failed: %s", attempt + 1, retries + 1, exc)
            if attempt == retries:
                raise RuntimeError(
                    f"LLM failed to return valid JSON after {retries + 1} attempts."
                ) from exc
