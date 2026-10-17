"""The LLM client works with any OpenAI-compatible server: Rakathon APIM today, the hospital's own model server later."""

from types import SimpleNamespace

import httpx
import pytest
from openai import APIStatusError
from pydantic import BaseModel

from app import llm
from app.config import get_settings


class Answer(BaseModel):
    code: str
    certain: bool


class FakeOpenAI:
    """Stands in for openai.OpenAI: remembers how it was built and answers from a script of responses / errors."""

    script: list = []
    calls: list = []
    init: dict = {}

    def __init__(self, **kwargs):
        type(self).init = kwargs
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._call("parse"), create=self._call("create")))

    def _call(self, kind):
        def call(**kwargs):
            type(self).calls.append((kind, kwargs))
            step = type(self).script.pop(0)
            if isinstance(step, Exception):
                raise step
            message = SimpleNamespace(parsed=step if kind == "parse" else None, content=step if kind == "create" else None, refusal=None)
            return SimpleNamespace(choices=[SimpleNamespace(message=message)])
        return call


def _status(code: int) -> APIStatusError:
    return APIStatusError(f"HTTP {code}", response=httpx.Response(code, request=httpx.Request("POST", "http://llm/v1")), body=None)


@pytest.fixture
def fake(monkeypatch, tmp_path):
    s = get_settings()
    for name, value in {"llm_cache_dir": str(tmp_path), "llm_auth": "api-key", "llm_output": "schema", "llm_api_key": "k",
                        "llm_model": "test-model", "llm_reasoning_effort": "low", "llm_temperature": None}.items():
        monkeypatch.setattr(s, name, value)
    monkeypatch.setattr(llm, "OpenAI", FakeOpenAI)
    monkeypatch.setattr(llm.time, "sleep", lambda _: None)
    FakeOpenAI.script, FakeOpenAI.calls = [], []
    return s


def test_rakathon_gateway_is_the_default(fake):
    FakeOpenAI.script = [Answer(code="C50.4", certain=True)]
    assert llm.structured("sys", "user", Answer) == Answer(code="C50.4", certain=True)
    assert FakeOpenAI.init["default_headers"] == {"api-key": "k"}
    kind, kwargs = FakeOpenAI.calls[0]
    assert kind == "parse" and kwargs["response_format"] is Answer and kwargs["reasoning_effort"] == "low"
    assert "temperature" not in kwargs


def test_hospital_server_with_bearer_key_and_json_mode(fake, monkeypatch):
    monkeypatch.setattr(fake, "llm_auth", "bearer")
    monkeypatch.setattr(fake, "llm_output", "json")
    monkeypatch.setattr(fake, "llm_reasoning_effort", "")
    monkeypatch.setattr(fake, "llm_temperature", 0.0)
    # a local reasoning model thinks aloud and wraps the JSON in a markdown fence
    FakeOpenAI.script = ['<think>pT1b, C50.4 ...</think>\n```json\n{"code": "C50.4", "certain": false}\n```']
    assert llm.structured("sys", "user", Answer) == Answer(code="C50.4", certain=False)
    assert FakeOpenAI.init["api_key"] == "k" and FakeOpenAI.init["default_headers"] == {}
    kind, kwargs = FakeOpenAI.calls[0]
    assert kind == "create" and kwargs["response_format"] == {"type": "json_object"} and kwargs["temperature"] == 0.0
    assert '"code"' in kwargs["messages"][0]["content"] and "reasoning_effort" not in kwargs  # the schema is in the prompt


def test_overloaded_server_and_off_schema_answers_are_retried_other_errors_are_not(fake, monkeypatch):
    FakeOpenAI.script = [_status(503), _status(429), Answer(code="C20", certain=True)]
    assert llm.structured("sys", "retry", Answer).code == "C20"
    assert len(FakeOpenAI.calls) == 3

    monkeypatch.setattr(fake, "llm_output", "json")
    FakeOpenAI.script = ['{"code": "C20"}', '{"code": "C20", "certain": true}']  # first answer misses a field
    assert llm.structured("sys", "json retry", Answer).certain is True

    FakeOpenAI.script = [_status(400)]
    with pytest.raises(APIStatusError):
        llm.structured("sys", "bad request", Answer)


def test_answers_are_cached_per_model(fake, monkeypatch):
    FakeOpenAI.script = [Answer(code="C50.4", certain=True)]
    llm.structured("sys", "same", Answer)
    assert llm.structured("sys", "same", Answer).code == "C50.4" and len(FakeOpenAI.calls) == 1  # from the cache
    monkeypatch.setattr(fake, "llm_model", "hospital-model")  # another model never reuses these answers
    FakeOpenAI.script = [Answer(code="C50.9", certain=False)]
    assert llm.structured("sys", "same", Answer).code == "C50.9"
