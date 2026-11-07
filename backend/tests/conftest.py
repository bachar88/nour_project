import uuid

import pytest

from app.chunking import build_corpus
from app.config import settings
from app.dev_fakes import FakeEmbedder, FakeLLM, FakeReranker
from app.rag import RagEngine


@pytest.fixture(scope="session")
def corpus():
    return build_corpus(settings)


@pytest.fixture
def make_engine(corpus):
    import chromadb

    def _make(llm_mode="quote", use_reranker=True):
        client = chromadb.EphemeralClient()
        s = settings.__class__(use_reranker=use_reranker, collection=f"t{uuid.uuid4().hex[:8]}")
        e = RagEngine(corpus, s, embedder=FakeEmbedder(),
                      reranker=FakeReranker() if use_reranker else None,
                      llm=FakeLLM(llm_mode), chroma_client=client)
        e.ensure_index()
        return e
    return _make
