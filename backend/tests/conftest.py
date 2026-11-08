import dataclasses

import pytest

from app.chunking import build_corpus
from app.config import settings
from app.dev_fakes import DEMO_OVERRIDES, FakeEmbedder, FakeLLM, MemoryStore
from app.rag import RagEngine


@pytest.fixture(scope="session")
def corpus():
    return build_corpus(settings)


@pytest.fixture(scope="session")
def store(corpus):
    return MemoryStore(corpus, FakeEmbedder())


@pytest.fixture
def make_engine(corpus, store):
    def _make(llm_mode="quote"):
        s = dataclasses.replace(settings, **DEMO_OVERRIDES)
        return RagEngine(corpus, s, FakeEmbedder(), store, FakeLLM(llm_mode))
    return _make
