"""GroqLLM builds the right request for gpt-oss (no network: fake HTTP transport)."""
import dataclasses
import json

import httpx
import pytest

from app.config import settings
from app.models import GroqLLM


def make(content, finish="stop", model="openai/gpt-oss-120b"):
    seen = {}

    def handler(req):
        seen.update(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": content}, "finish_reason": finish}],
                                         "usage": {"total_tokens": 900}})

    s = dataclasses.replace(settings, groq_api_key="k", groq_model=model)
    return GroqLLM(s, client=httpx.Client(transport=httpx.MockTransport(handler))), seen


def test_gpt_oss_request_hides_reasoning():
    llm, sent = make("الجواب: نعم.\nالدليل: «نص» [1]")
    text, tokens = llm.complete([{"role": "user", "content": "x"}])
    assert text.startswith("الجواب") and tokens == 900
    assert sent["model"] == "openai/gpt-oss-120b"
    assert sent["include_reasoning"] is False and "reasoning_format" not in sent  # not supported for GPT-OSS
    assert sent["reasoning_effort"] == "low"
    assert sent["max_completion_tokens"] == 1024


def test_other_models_get_no_reasoning_params():
    llm, sent = make("ok", model="allam-2-7b")
    llm.complete([{"role": "user", "content": "x"}])
    assert "reasoning_effort" not in sent and "include_reasoning" not in sent


def test_empty_answer_after_thinking_is_reported():
    llm, _ = make("", finish="length")
    with pytest.raises(RuntimeError, match="MAX_TOKENS"):
        llm.complete([{"role": "user", "content": "x"}])
