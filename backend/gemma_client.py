"""
Async wrapper around Google's Generative Language API for Gemma, with:
  - live token streaming (streamGenerateContent + SSE),
  - a global rate limiter (the key is capped at ~15 requests/min),
  - robust JSON extraction with a strict self-repair retry,
  - logging so you can watch the swarm work from the terminal.

NOTE: this is the Gemini-style endpoint, NOT OpenAI-compatible. Gemma here has
no separate system role and no reliable function-calling, so we fold "system"
into the first user turn and ask for JSON inside a ```json fence.
"""
from __future__ import annotations

import asyncio
import collections
import json
import logging
import os
import re
import time
from typing import Any, Awaitable, Callable

import httpx
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger("swarm.gemma")

from contextvars import ContextVar

API_KEY = os.getenv("GEMMA_API_KEY", "")
MODEL = os.getenv("GEMMA_MODEL", "gemma-4-31b-it")
BASE_URL = os.getenv(
    "GEMMA_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models"
)

OnToken = Callable[[str], Awaitable[None]]

# Context variables for dynamic request-scoped routing
current_model: ContextVar[str] = ContextVar("current_model", default="")
current_api_key: ContextVar[str] = ContextVar("current_api_key", default="")

GOOGLE_MODELS = {
    "gemma-4-31b-it",
    "gemini-3.5-flash",
    "gemini-3.1-pro-preview",
}
ANTHROPIC_MODELS = {
    "claude-sonnet-4-6",
    "claude-opus-4-8",
}


class GemmaError(RuntimeError):
    pass


# ── Rate limiter: never exceed ~14 requests per rolling 60s ────────────────────
_RATE_MAX = 14
_RATE_WINDOW = 60.0
_calls: collections.deque[float] = collections.deque()
_rate_lock = asyncio.Lock()


async def _rate_gate(use_limiter: bool) -> None:
    if not use_limiter:
        return
    while True:
        async with _rate_lock:
            now = time.monotonic()
            while _calls and now - _calls[0] > _RATE_WINDOW:
                _calls.popleft()
            if len(_calls) < _RATE_MAX:
                _calls.append(now)
                return
            wait = _RATE_WINDOW - (now - _calls[0]) + 0.05
        log.info("rate limit reached, waiting %.1fs", wait)
        await asyncio.sleep(wait)


async def generate(
    prompt: str,
    *,
    system: str | None = None,
    temperature: float = 0.7,
    max_tokens: int = 4096,
    client: httpx.AsyncClient | None = None,
    on_token: OnToken | None = None,
    retries: int = 2,
    label: str = "agent",
) -> str:
    """Stream one completion, calling on_token for each delta; return full text."""
    model_name = current_model.get() or MODEL
    api_key_val = current_api_key.get()

    if not api_key_val:
        # Fallback to environment variables
        if model_name in ANTHROPIC_MODELS:
            api_key_val = os.getenv("ANTHROPIC_API_KEY", "")
        else:
            api_key_val = API_KEY

    if not api_key_val:
        if model_name in ANTHROPIC_MODELS:
            raise GemmaError("Anthropic API Key is not set. Please configure it in Settings (🔑 Key).")
        else:
            raise GemmaError("Gemini API Key is not set. Please configure it in Settings (🔑 Key) or check your server configuration.")

    is_google = model_name not in ANTHROPIC_MODELS
    # Limit only when calling standard Google models using the default system API key
    use_limiter = is_google and (api_key_val == API_KEY)

    # Prepare payload based on provider
    if is_google:
        text = f"{system.strip()}\n\n{prompt.strip()}" if system else prompt.strip()
        payload: dict[str, Any] = {
            "contents": [{"role": "user", "parts": [{"text": text}]}],
            "generationConfig": {"temperature": temperature, "maxOutputTokens": max_tokens},
        }
    else:
        payload = {
            "model": model_name,
            "messages": [{"role": "user", "content": prompt.strip()}],
            "max_tokens": max_tokens,
            "temperature": temperature,
            "stream": True,
        }
        if system:
            payload["system"] = system.strip()

    owns_client = client is None
    if owns_client:
        client = httpx.AsyncClient(timeout=httpx.Timeout(300.0, connect=15.0))
    try:
        last_err: Exception | None = None
        for attempt in range(retries + 1):
            try:
                await _rate_gate(use_limiter)
                log.info("[%s] -> request (%s, attempt %d)", label, model_name, attempt + 1)
                
                if is_google:
                    endpoint = f"{BASE_URL}/{model_name}:streamGenerateContent?alt=sse&key={api_key_val}"
                    full = await _stream_google(client, endpoint, payload, on_token)
                else:
                    full = await _stream_anthropic(client, payload, api_key_val, on_token)
                
                if not full:
                    raise GemmaError("empty response from model")
                log.info("[%s] <- %d chars", label, len(full))
                return full
            except (httpx.HTTPError, GemmaError) as e:
                last_err = e
                detail = f"{type(e).__name__}: {e}".strip()
                log.warning("[%s] error: %s", label, detail)
                if attempt < retries:
                    await asyncio.sleep(2.0 * (attempt + 1))
                else:
                    raise GemmaError(detail) from e
        raise GemmaError(f"{type(last_err).__name__}: {last_err}")
    finally:
        if owns_client:
            await client.aclose()


async def _stream_google(
    client: httpx.AsyncClient, endpoint: str, payload: dict, on_token: OnToken | None
) -> str:
    chunks: list[str] = []
    async with client.stream("POST", endpoint, json=payload) as resp:
        if resp.status_code != 200:
            body = (await resp.aread()).decode("utf-8", "replace")
            raise GemmaError(f"Google API HTTP {resp.status_code}: {body[:300]}")
        async for line in resp.aiter_lines():
            if not line or not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if data == "[DONE]":
                break
            try:
                obj = json.loads(data)
            except json.JSONDecodeError:
                continue
            delta = _delta_text(obj)
            if delta:
                chunks.append(delta)
                if on_token:
                    await on_token(delta)
    return "".join(chunks).strip()


async def _stream_anthropic(
    client: httpx.AsyncClient, payload: dict, api_key: str, on_token: OnToken | None
) -> str:
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    chunks: list[str] = []
    async with client.stream("POST", "https://api.anthropic.com/v1/messages", json=payload, headers=headers) as resp:
        if resp.status_code != 200:
            body = (await resp.aread()).decode("utf-8", "replace")
            raise GemmaError(f"Anthropic API HTTP {resp.status_code}: {body[:500]}")
        
        current_event = None
        async for line in resp.aiter_lines():
            line = line.strip()
            if not line:
                continue
            if line.startswith("event:"):
                current_event = line[6:].strip()
            elif line.startswith("data:"):
                data = line[5:].strip()
                if current_event == "content_block_delta":
                    try:
                        obj = json.loads(data)
                        delta = obj.get("delta", {}).get("text", "")
                        if delta:
                            chunks.append(delta)
                            if on_token:
                                await on_token(delta)
                    except json.JSONDecodeError:
                        continue
    return "".join(chunks).strip()


def _delta_text(obj: dict) -> str:
    try:
        parts = obj["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except (KeyError, IndexError):
        return ""


async def generate_json(prompt: str, **kwargs: Any) -> dict | list:
    """Stream + parse JSON, with one strict self-repair retry on parse failure."""
    raw = await generate(prompt, **kwargs)
    try:
        return _parse_json(raw)
    except GemmaError:
        log.warning("[%s] JSON parse failed, repairing", kwargs.get("label", "agent"))
        repair = (
            prompt
            + "\n\nIMPORTANT: Do not restate the task or think out loud. Reply with "
            "ONLY the final JSON object inside a single ```json code fence and nothing else."
        )
        kwargs["temperature"] = 0.1
        kwargs["max_tokens"] = max(int(kwargs.get("max_tokens", 4096)), 6000)
        kwargs.pop("on_token", None)  # repair output is noise, don't stream it
        raw = await generate(repair, **kwargs)
        return _parse_json(raw)


def _parse_json(raw: str) -> dict | list:
    s = raw.strip()
    fence = re.search(r"```(?:json)?\s*(.*?)```", s, re.DOTALL)
    if fence:
        s = fence.group(1).strip()
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass
    for open_ch, close_ch in (("{", "}"), ("[", "]")):
        start = s.find(open_ch)
        end = s.rfind(close_ch)
        if start != -1 and end > start:
            try:
                return json.loads(s[start : end + 1])
            except json.JSONDecodeError:
                continue
    raise GemmaError(f"Could not parse JSON from model output:\n{raw[:400]}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    async def _smoke() -> None:
        print("Streaming test:\n")
        async def show(t: str) -> None:
            print(t, end="", flush=True)
        await generate("Count from 1 to 5 slowly.", on_token=show, label="smoke")
        print("\n\ndone.")

    asyncio.run(_smoke())
