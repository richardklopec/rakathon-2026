"""The only place that talks to the LLM gateway (Rakathon APIM, OpenAI-compatible)."""

import hashlib
import json
import time

from openai import APIStatusError, OpenAI
from pydantic import BaseModel

from app.config import get_settings

_MAX_RETRIES = 5


def _client() -> OpenAI:
    s = get_settings()
    # The gateway authenticates with an `api-key` header, not `Authorization: Bearer`.
    return OpenAI(base_url=s.llm_base_url, api_key="unused", default_headers={"api-key": s.llm_api_key})


def _cache_path(key: str):
    d = get_settings().data_dir / "llm-cache"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{key}.json"


def structured(system: str, user: str, schema: type[BaseModel]) -> BaseModel:
    """Call the chat model and parse its answer into `schema`. Answers are cached by input hash."""
    s = get_settings()
    key = hashlib.sha256(json.dumps([s.llm_model, s.llm_reasoning_effort, system, user, schema.__name__]).encode()).hexdigest()
    cached = _cache_path(key)
    if cached.exists():
        return schema.model_validate_json(cached.read_text(encoding="utf-8"))

    client = _client()
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.parse(
                model=s.llm_model,
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                response_format=schema,
                **({"reasoning_effort": s.llm_reasoning_effort} if s.llm_reasoning_effort else {}),
            )
            break
        except APIStatusError as e:
            # 429 = gateway rate limit -> exponential backoff; anything else is a real error
            if e.status_code != 429 or attempt == _MAX_RETRIES - 1:
                raise
            time.sleep(2**attempt)

    result = resp.choices[0].message.parsed
    cached.write_text(result.model_dump_json(), encoding="utf-8")
    return result


def embed(texts: list[str]) -> list[list[float]]:
    s = get_settings()
    if not s.embedding_model:
        raise RuntimeError("EMBEDDING_MODEL is not configured")
    resp = _client().embeddings.create(model=s.embedding_model, input=texts)
    return [d.embedding for d in resp.data]
