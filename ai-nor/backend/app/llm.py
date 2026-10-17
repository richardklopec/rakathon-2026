"""The only place that talks to the LLM: any OpenAI-compatible server (Rakathon APIM today, the hospital's own later).

Switching servers is configuration only (LLM_BASE_URL, LLM_MODEL, LLM_AUTH, LLM_OUTPUT, ...; see app/config.py):
the rest of the app calls `structured()` and gets a validated pydantic object either way.
"""

import hashlib
import json
import re
import time
from pathlib import Path

from openai import APIConnectionError, APIStatusError, OpenAI
from pydantic import BaseModel, ValidationError

from app.config import get_settings

_MAX_RETRIES = 5
# rate limit (gateway) and an overloaded / restarting model server: worth waiting; anything else is a real error
_RETRY_STATUS = {429, 500, 502, 503, 504}


def _client() -> OpenAI:
    s = get_settings()
    headers, key = {}, "unused"
    if s.llm_auth == "api-key":  # Rakathon APIM authenticates with an `api-key` header, not `Authorization: Bearer`
        headers["api-key"] = s.llm_api_key
    elif s.llm_auth == "bearer":
        key = s.llm_api_key or "unused"
    return OpenAI(base_url=s.llm_base_url, api_key=key, default_headers=headers, timeout=s.llm_timeout, max_retries=0)


def _cache_path(key: str):
    s = get_settings()
    d = Path(s.llm_cache_dir) if s.llm_cache_dir else s.data_dir / "llm-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def _json_text(content: str) -> str:
    """The JSON object out of a JSON-mode answer: without the reasoning (<think>…</think>) and markdown fences."""
    content = re.sub(r"(?s)<think>.*?</think>", "", content or "")
    start, end = content.find("{"), content.rfind("}")
    return content[start:end + 1] if start >= 0 and end > start else content


def _ask(client: OpenAI, system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    s = get_settings()
    extra = {}
    if s.llm_reasoning_effort:
        extra["reasoning_effort"] = s.llm_reasoning_effort
    if s.llm_temperature is not None:
        extra["temperature"] = s.llm_temperature
    if s.llm_output == "schema":  # the server constrains the answer to the schema
        resp = client.chat.completions.parse(
            model=s.llm_model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
            response_format=schema,
            **extra,
        )
        message = resp.choices[0].message
        if message.parsed is None:
            raise ValueError(f"model nevrátil odpověď ve schématu {schema.__name__}: {message.refusal or message.content!r:.200}")
        return message.parsed
    # JSON mode: the schema goes into the prompt and the answer is validated here, with the same pydantic model
    instructions = (f"{system}\n\nAnswer with a single JSON object that matches this JSON Schema, and nothing else:\n"
                    f"{json.dumps(schema.model_json_schema(), ensure_ascii=False)}")
    resp = client.chat.completions.create(
        model=s.llm_model,
        messages=[{"role": "system", "content": instructions}, {"role": "user", "content": user}],
        response_format={"type": "json_object"},
        **extra,
    )
    return schema.model_validate_json(_json_text(resp.choices[0].message.content))


def structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """Call the chat model and parse its answer into `schema`. Answers are cached by input hash."""
    s = get_settings()
    key = hashlib.sha256(json.dumps([s.llm_model, s.llm_reasoning_effort, system, user, schema.__name__]).encode()).hexdigest()
    cached = _cache_path(key)
    if cached.exists():
        return schema.model_validate_json(cached.read_text(encoding="utf-8"))

    client = _client()
    for attempt in range(_MAX_RETRIES):
        last = attempt == _MAX_RETRIES - 1
        try:
            result = _ask(client, system, user, schema)
            break
        except APIStatusError as e:
            if e.status_code not in _RETRY_STATUS or last:
                raise
        except (APIConnectionError, ValidationError):  # server unreachable / timed out; JSON mode answer off the schema
            if last:
                raise
        time.sleep(2**attempt)

    cached.write_text(result.model_dump_json(), encoding="utf-8")
    return result


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if not s.embedding_model:
        raise RuntimeError("EMBEDDING_MODEL is not configured")
    resp = _client().embeddings.create(model=s.embedding_model, input=texts)
    return [d.embedding for d in resp.data]
