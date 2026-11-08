"""GroqLLM builds the right request for gpt-oss (no network: the Groq client is replaced)."""
from types import SimpleNamespace

import pytest

from app.config import settings
from app.models import GroqLLM


class FakeCompletions:
    def __init__(self, content, finish="stop"):
        self.content, self.finish, self.kwargs = content, finish, None

    def create(self, **kwargs):
        self.kwargs = kwargs
        msg = SimpleNamespace(content=self.content)
        return SimpleNamespace(choices=[SimpleNamespace(message=msg, finish_reason=self.finish)],
                               usage=SimpleNamespace(total_tokens=900))


def make(content, finish="stop", model="openai/gpt-oss-120b"):
    llm = GroqLLM.__new__(GroqLLM)  # skip __init__ (no API key / network)
    llm.settings = settings.__class__(groq_model=model)
    fake = FakeCompletions(content, finish)
    llm.client = SimpleNamespace(chat=SimpleNamespace(completions=fake))
    return llm, fake


def test_gpt_oss_request_hides_reasoning():
    llm, fake = make("الجواب: نعم.\nالدليل: «نص» [1]")
    text, tokens = llm.complete([{"role": "user", "content": "x"}])
    assert text.startswith("الجواب") and tokens == 900
    assert fake.kwargs["model"] == "openai/gpt-oss-120b"
    assert fake.kwargs["reasoning_format"] == "hidden"
    assert fake.kwargs["reasoning_effort"] == "low"
    assert fake.kwargs["max_completion_tokens"] == 1024


def test_other_models_get_no_reasoning_params():
    llm, fake = make("ok", model="allam-2-7b")
    llm.complete([{"role": "user", "content": "x"}])
    assert "reasoning_format" not in fake.kwargs


def test_empty_answer_after_thinking_is_reported():
    llm, _ = make("", finish="length")
    with pytest.raises(RuntimeError):
        llm.complete([{"role": "user", "content": "x"}])
